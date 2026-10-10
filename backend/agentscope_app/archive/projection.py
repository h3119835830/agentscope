"""Read-only task archives over authoritative tables; no second policy store."""
import base64
import json
import re
from fastapi import HTTPException
from .. import db
from ..agent_bridge.api import clean

CATEGORIES = ("timeline", "tools", "kernel", "audit")
PRIVATE = re.compile(r"(?i)(token|credential|secret|password|authorization|reasoning|thinking|chain.of.thought|raw.stream|native_execution_context|serialized)")
CLOSURE_KINDS = ("closed", "close_failed", "closure_requested", "cleanup_result", "task_stopped", "task_execution_finished", "revocation")
PREPARATION_KINDS = ("created", "startup_generation", "startup_clarification", "startup_review_required", "startup_confirmed", "startup_rejected")

def safe(value):
    """Defense in depth after field selection; never traverse opaque native streams."""
    if isinstance(value, dict):
        if value.get("type") in ("reasoning", "thinking", "reasoning_content", "redacted_thinking"):
            return {"redacted": True}
        return {k:safe(v) for k,v in value.items() if not PRIVATE.search(k)}
    if isinstance(value, list): return [safe(v) for v in value]
    if isinstance(value, str):
        value = re.sub(r"(?is)<(?:think|thinking|reasoning)>.*?</(?:think|thinking|reasoning)>", "[PRIVATE CONTENT OMITTED]", value)
        value = clean(value)
        value = re.sub(r"(?i)\b(token|secret|credential|authorization|refresh[_-]?token)\s*[:=]\s*[^\s,;]+", r"\1=[REDACTED]", value)
        value = re.sub(r"(?i)(https?://)[^/@\s]+:[^/@\s]+@", r"\1[REDACTED]@", value)
        return re.sub(r"\bsk-[A-Za-z0-9_-]{12,}\b", "[REDACTED]", value)
    return value

def decode(value):
    try: return json.loads(value) if value else {}
    except (ValueError, TypeError): return {}

def pick(value, *keys):
    return {k:value[k] for k in keys if isinstance(value, dict) and k in value}

def tables(con):
    return {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}

def index(con):
    """Only project identifiers and ordering metadata before applying pagination."""
    available=tables(con)
    parts=[]
    def add(table, identity, time, stage, category, kind, predicate="task_id=:task", milestone="record"):
        if table not in available: return
        parts.append(f"SELECT '{table}' AS source,CAST({identity} AS TEXT) AS source_id,'{milestone}' AS milestone,"
                     f"'{table}:'||CAST({identity} AS TEXT)||':{milestone}' AS id,COALESCE({time},'') AS time,"
                     f"{stage} AS stage,'{category}' AS category,{kind} AS kind FROM {table} WHERE {predicate}")
    add("tasks","id","created_at","'preparation'","timeline","'task_created'","id=:task")
    add("tasks","id","ended_at","'closure'","timeline","'task_ended'","id=:task AND ended_at IS NOT NULL","ended")
    add("bootstrap_contexts","task_id","created_at","'preparation'","timeline","'task_context'")
    add("bootstrap_sources","id","(SELECT created_at FROM bootstrap_contexts WHERE task_id=:task)","'preparation'","timeline","'file_snapshot'")
    add("evidence","id","collected_at","'preparation'","timeline","'evidence'")
    job_where="kind='task_bootstrap' AND json_extract(input_json,'$.task_id')=:task"
    add("history_jobs","id","created_at","'preparation'","timeline","'startup_job'",job_where)
    add("history_jobs","id","started_at","'preparation'","timeline","'startup_started'",job_where+" AND started_at IS NOT NULL","started")
    add("history_jobs","id","finished_at","'preparation'","timeline","'startup_finished'",job_where+" AND finished_at IS NOT NULL","finished")
    add("bootstrap_proposals","id","created_at","'preparation'","timeline","'startup_candidate'")
    add("bootstrap_results","task_id","created_at","'preparation'","timeline","'startup_result'")
    add("workspace_scene_reads","id","updated_at","'preparation'","timeline","'workspace_scene_read'")
    if "workspace_scene_reads" in available:
        scene_job="kind='workspace_scene_read' AND EXISTS (SELECT 1 FROM workspace_scene_reads s WHERE s.job_id=history_jobs.id AND s.task_id=:task)"
        add("history_jobs","id","created_at","'preparation'","timeline","'scene_read_queued'",scene_job)
        add("history_jobs","id","finished_at","'preparation'","timeline","'scene_read_finished'",scene_job+" AND finished_at IS NOT NULL","finished")
        add("scene_read_events","id","occurred_at","'preparation'","tools","tool","EXISTS (SELECT 1 FROM workspace_scene_reads s WHERE s.id=scene_read_events.read_id AND s.task_id=:task)")
    add("policy_versions","id","created_at","'preparation'","timeline","'policy_version'")
    add("policy_versions","id","approved_at","'preparation'","timeline","'policy_review'","task_id=:task AND approved_at IS NOT NULL","review")
    add("history_compilations","id","created_at","'preparation'","timeline","'compilation'")
    add("history_deployments","id","created_at","'execution'","timeline","'deployment'")
    add("history_deployments","id","ended_at","'closure'","timeline","'deployment_ended'","task_id=:task AND ended_at IS NOT NULL","ended")
    add("managed_jobs","id","created_at","'execution'","timeline","'runtime_job'")
    closure=",".join("'"+k+"'" for k in CLOSURE_KINDS)
    prep=",".join("'"+k+"'" for k in PREPARATION_KINDS)
    stage=f"CASE WHEN kind IN ({closure}) THEN 'closure' WHEN kind IN ({prep}) THEN 'preparation' ELSE 'execution' END"
    add("managed_events","id","occurred_at",stage,"timeline","kind","task_id=:task AND kind NOT IN ('kernel','tool_start','tool_result')")
    add("managed_events","id","occurred_at","'execution'","tools","kind","task_id=:task AND kind IN ('tool_start','tool_result')")
    add("managed_events","id","occurred_at","'execution'","kernel","kind","task_id=:task AND kind='kernel'")
    add("runtime_events","id","occurred_at","'execution'","kernel","kind","task_id=:task AND NOT EXISTS (SELECT 1 FROM managed_events m WHERE m.task_id=runtime_events.task_id AND m.kind='kernel' AND m.event_key=runtime_events.dedupe_key)")
    add("scope_requests","id","created_at","'execution'","timeline","'scope_request'")
    add("scope_requests","id","reviewed_at","'execution'","timeline","'scope_review'","task_id=:task AND reviewed_at IS NOT NULL","review")
    audit_stage=f"CASE WHEN action IN ({closure}) THEN 'closure' WHEN action IN ('policy_approved','policy_rejected','policy_generated','task_prepared') THEN 'preparation' ELSE 'execution' END"
    add("audit_log","id","created_at",audit_stage,"audit","action")
    # Review/apply/closure receipts are essential timeline events even when tools/audit are folded.
    add("audit_log","id","created_at",audit_stage,"timeline","action","task_id=:task AND (action LIKE '%review%' OR action LIKE '%approv%' OR action LIKE '%reject%' OR action LIKE '%launch%' OR action LIKE '%stop%' OR action LIKE '%finished%' OR action LIKE '%fail%')","receipt")
    tool_where="EXISTS (SELECT 1 FROM history_jobs j WHERE j.id=bootstrap_tool_events.job_id AND json_extract(j.input_json,'$.task_id')=:task) OR EXISTS (SELECT 1 FROM bootstrap_proposals p WHERE p.job_id=bootstrap_tool_events.job_id AND p.task_id=:task)"
    add("bootstrap_tool_events","id","occurred_at","'preparation'","tools","tool","("+tool_where+")")
    add("agent_feedback","id","created_at","'execution'","timeline","kind")
    return " UNION ALL ".join(parts)

def require_task(con, task_id):
    row=con.execute("SELECT * FROM tasks WHERE id=?",(task_id,)).fetchone()
    if not row: raise HTTPException(404,"任务不存在")
    return dict(row)

def cursor_encode(task_id,category,event):
    return base64.urlsafe_b64encode(json.dumps([task_id,category,event["time"],event["id"]],separators=(",",":")).encode()).decode().rstrip("=")

def cursor_decode(value,task_id,category):
    try:
        if len(value)>2048: raise ValueError()
        data=json.loads(base64.urlsafe_b64decode(value+"="*(-len(value)%4)))
        if not isinstance(data,list) or len(data)!=4 or data[:2]!=[task_id,category] or not all(isinstance(x,str) for x in data): raise ValueError()
        return data[2:]
    except Exception: raise HTTPException(422,"无效的档案分页游标")

def event_row(con,item):
    key="task_id" if item["source"] in ("bootstrap_contexts","bootstrap_results") else "id"
    return dict(con.execute(f"SELECT * FROM {item['source']} WHERE {key}=?",(item["source_id"],)).fetchone())

def compiler_projection(value):
    return pick(value,"ok","status","rule_count","rules","warnings","errors","normalization")

def proposal_projection(value):
    # Model explanation is a public submitted candidate field, never a private chain of thought.
    result=pick(value,"decision","allowed_write_dirs","allow_output","protected_paths","evidence_ids","identified_statements","explanation","hash","compiled_dsl","compiled_dsl_hash","unresolved_requests","normalization")
    if "compile" in value: result["compile"]=compiler_projection(value["compile"])
    draft=value.get("draft")
    if isinstance(draft,dict):result["draft"]=pick(draft,"atoms","guidance","dsl_text","evidence_ids")
    return result

def receipt_projection(value):
    return pick(value,"status","stopped","cleanup_status","cleanup_confirmed","error","reason","domain_id","runner_pid","watch_pid","attempted_domain_id","attempted_runner_pid","version","passed","exit_code","returncode","execution_exit","remaining_processes","revoked","temporary_grants","resources","native_stop","broker_stop","broker_status","session_stopped","domain_revoked","cleanup","errors","quiesced_pids","writable_fds_and_mappings")

def kernel_projection(value):
    result=pick(value,"id","event_id","event_key","op","operation","target","pid","ppid","domain_id","process_domain_id","rule_id","time","timestamp","blocked","decision","kernel_call_tag")
    if isinstance(value.get("rule"),dict):result["rule"]=pick(value["rule"],"rule_id","name","reason","clause_hash","clause_op","target_pattern")
    return result

def action_source(kind,payload):
    # Provenance comes from recorded event type/flags, never PID coincidence.
    if kind in ("operation_verified","native_sdk_verification") or payload.get("verification_probe") is True or payload.get("native_sdk_verification") is True:return "independent_probe"
    if kind in ("tool_start","tool_result"):return "native_tool"
    if kind=="kernel":return "kernel"
    if kind in ("agent_refusal","agent_deferral","agent_response"):return "agent_report"
    if kind in ("request","startup_clarification") and payload.get("actor") in ("native_user","user","administrator","DSH","authenticated_operator"):return "user_request"
    if kind in ("control_pause","policy_active","failure","closed","close_failed","closure_requested","cleanup_result","task_stopped","task_execution_finished","revocation","review_pending","change_review","candidate_invalidated","change_apply_failed","request_resolved","startup_confirmed","startup_rejected"):return "controller"
    return "not_recorded"

def managed_detail(row):
    p=decode(row.get("payload_json"));kind=row["kind"]
    base=pick(p,"job_id","version","revision","session_id","turn","domain_id","runner_pid","watch_pid","call_id","tool_call_id","name","succeeded","target","pid","operation","decision","reason","error","actor","authority","event_ids","evidence_ids","request_ids","request_id","accepted_request_event_id","candidate_hash","hash","expected_hash","temporary_grants","replacement_stopped","before_native_admission","source","original_request_preserved","cleanup_confirmed","cleanup_status","change","base_version","phase","confirmation","policy_hash","baseline_hash","context_hash","proposal_hash","context_revision")
    base["action_source"]=action_source(kind,p)
    for name in ("verification_probe","native_sdk_verification"):
        if isinstance(p.get(name),bool):base[name]=p[name]
    base.update(pick(p,"classification","expected","effect_verified","before_hash","after_hash","correlation","kernel_event_ids"))
    if kind=="operation_verified":
        probe=p.get("probe",{})
        if isinstance(probe,dict):
            base["probe"]=pick(probe,"operation","target","pid","ppid","attempted","blocked","success","errno","error","expected","passed")
            base.update(pick(probe,"operation","target","pid"))
        if isinstance(p.get("probe_binding"),dict):base["probe_binding"]=pick(p["probe_binding"],"domain_verified","cgroup_verified","process_cgroup","starttime","pid","domain_id")
        if isinstance(p.get("kernel_events"),list):base["kernel_events"]=[kernel_projection(e) for e in p["kernel_events"] if isinstance(e,dict)]
        base["meaning"]="independent_operation_probe; classification is a historical verification receipt"
    if kind in ("request","startup_clarification","change_review") and p.get("actor","administrator") in ("native_user","user","administrator","DSH","authenticated_operator"):base["user_request"]=p.get("text")
    if kind=="runtime_observation":
        base.update(pick(p,"category","type","seq","content_hash"))
    if kind=="candidate": base["proposal"]=proposal_projection(p.get("proposal",{}))
    for name in ("receipt","cleanup","binding","verification","result"):
        if isinstance(p.get(name),dict):base[name]=receipt_projection(p[name])
    if kind=="kernel":
        event=p.get("event",{})
        base["kernel"]=kernel_projection(event)
        base.update(pick(event,"target","pid"))
        if "op" in event or "operation" in event:base["operation"]=event.get("op",event.get("operation"))
        if "process_domain_id" in event:base["domain_id"]=event["process_domain_id"]
        base["meaning"]="kernel_denial"
    elif kind in ("tool_start","tool_result"):
        base["meaning"]="tool_outcome; success is not proof of kernel permission"
        # Never expose serialized tool arguments or results; controller retains metadata only.
        base["result"]="started" if kind=="tool_start" else "success" if p.get("succeeded") is True else "failure" if p.get("succeeded") is False else "not_recorded"
    elif kind=="control_pause":base["meaning"]="control_plane_gate; not kernel denial"
    elif kind in ("agent_refusal","agent_deferral"):base["meaning"]="agent_report; not kernel enforcement"
    return base

def detail_payload(con,item,row,include_records=True):
    source=item["source"]
    if source=="managed_events": return managed_detail(row)
    if source=="tasks":
        if item["kind"]=="task_created":return pick(row,"prompt","workspace","created_at")|{"status":"created"}
        return pick(row,"workspace","ended_at")|{"status":"ended"}
    if source=="bootstrap_contexts":
        ctx=decode(row.get("context_json"))
        return {**pick(row,"context_hash","scenario_id"),**pick(ctx,"declared_constraints","execution_constraints","platform_constraints","environment","mapping","assets","scenario_commit","scenario_hash","accepted_task_constraints","workspace_scene_read")}
    if source=="bootstrap_sources": return pick(row,"role","path","content_hash") | {"snapshot":"persisted_source_hash","content":"not_exported"}
    if source=="evidence":return pick(row,"kind","title","uri","file_path","commit_sha","line_start","line_end","content_sha256","excerpt")
    if source=="history_jobs" and row.get("kind")=="workspace_scene_read":return pick(row,"status","error","created_at","started_at","finished_at")|{"read_only":True,"action_source":"pi_scene_reader"}
    if source=="history_jobs":return pick(row,"status","error","created_at","started_at","finished_at","retry_of")|{"result":receipt_projection(decode(row.get("result_json")))}
    if source=="bootstrap_proposals":return pick(row,"job_id","state","context_hash","content_hash")|{"proposal":proposal_projection(decode(row.get("proposal_json"))),"validation":pick(decode(row.get("validation_json")),"ok","errors","warnings","source_reads","normalization")|{"compiler":compiler_projection(decode(row.get("validation_json")).get("compiler",{}))}}
    if source=="bootstrap_results":return {"result":receipt_projection(decode(row.get("result_json")))}
    if source=="workspace_scene_reads":
        from ..workspaces.scene_read import get
        reading=get(row['workspace_id'],row['id'])
        return pick(reading,"status","read_only","manifest_hash","source_generation","draft","draft_hash","evidence","runtime","created_at","updated_at")|{"action_source":"pi_scene_reader","meaning":"historical read-only task draft; adoption is not policy loading"}
    if source=="scene_read_events":return {"tool":row['tool'],"receipt":decode(row.get('metadata_json')),"action_source":"pi_scene_reader"}
    if source=="policy_versions":return pick(row,"version","layer","status","dsl_text","compile_state","change_summary","approved_by","approved_at")|{"evidence_ids":decode(row.get("evidence_ids")),"source_strategy_ids":decode(row.get("source_strategy_ids")),"compile":compiler_projection(decode(row.get("compile_json")))}
    if source=="history_compilations":return pick(row,"policy_version_id","artifact_id","input_hash","state","compiler_version")|{"compile":compiler_projection(decode(row.get("result_json")))}
    if source=="history_deployments":return pick(row,"policy_version_id","bundle_hash","status","domain_id","runner_pid","created_at","ended_at")|{"receipt":receipt_projection(decode(row.get("receipt_json")))}
    if source=="managed_jobs":
        ctx=decode(row.get("context_json"));p=decode(row.get("proposal_json"))
        value=pick(row,"status","revision","policy_hash","error","created_at")|{"decision":p.get("decision"),"proposal":proposal_projection(p),"session_id":ctx.get("session_id"),"request_evidence_id":ctx.get("request_evidence_id")}
        value["public_requests"]=[pick(x,"evidence_id","text","kind","actor","session_id","turn") for x in ctx.get("public_task_context",[]) if x.get("actor") in ("native_user","user","administrator","DSH")]
        # Existing structured policy records supply mapped DSL, provenance and evidence.
        if p and include_records:
            try:
                from ..managed import records
                task=require_task(con,row["task_id"])
                state_row=con.execute("SELECT state_json FROM managed_tasks WHERE task_id=?",(row["task_id"],)).fetchone()
                if state_row:
                    mapped=records.runtime_statement_records(con,task,decode(state_row[0]),row,True)
                    for record in mapped:
                        record["status"]="historical_receipt"
                        record["loading"]={k:v for k,v in record.get("loading",{}).items() if k not in ("active","effective")}
                        for link in record.get("normalization",{}).get("links",[]):
                            for ref in ("current_loading","first_loading"):
                                if isinstance(link.get(ref),dict):link[ref].pop("active",None)
                    value["policy_records"]=mapped
            except (KeyError,ValueError,TypeError):
                value["policy_records_status"]="not_recorded"
        return value
    if source=="scope_requests":return pick(row,"kind","requested_change","path","justification","status","requested_by","reviewed_by","reviewed_at","resulting_version")|{"result":receipt_projection(decode(row.get("result_json")))}
    if source=="audit_log":
        p=decode(row.get("details_json"))
        return pick(row,"action","actor")|{"receipt":receipt_projection(p)|pick(p,"notes","decision","request_id","proposal_id","version","candidate_id","hash")}
    if source=="runtime_events":return pick(row,"kind","operation","target","decision","reason")|{"meaning":"persisted_runtime_event; inspect decision before treating as denial"}
    if source=="bootstrap_tool_events":
        p=decode(row.get("input_json"));out=decode(row.get("output_json"))
        return {"tool":row["tool"],"job_id":row["job_id"],"input_metadata":pick(p,"source_id","id","query"),"result_metadata":pick(out,"ok","status","state","content_hash","proposal_id","proposal_hash","errors","warnings")}
    if source=="agent_feedback":return pick(row,"run_key","snapshot_hash","kind","operation","target","summary")
    return {}

def project(con,item,with_detail=False):
    row=event_row(con,item)
    detail=safe(detail_payload(con,item,row,include_records=with_detail))
    result={**dict(item),"task_id":row.get("task_id",row.get("id")),"job_id":row.get("job_id",row["id"] if item["source"] in ("history_jobs","managed_jobs") else None),"version":row.get("version",detail.get("version")),"status":row.get("status",row.get("state",detail.get("result","recorded"))),"evidence_refs":detail.get("evidence_ids",detail.get("proposal",{}).get("evidence_ids",[])),"history_only":True,"summary":item["kind"],"detail_available":True}
    if item["kind"]=="task_created":result["status"]="created"
    elif item["kind"]=="task_ended":result["status"]="ended"
    elif item["kind"]=="startup_started":result["status"]="started"
    if item["source"]=="managed_events":
        payload=decode(row.get("payload_json"))
        result["job_id"]=payload.get("job_id")
        if not result["job_id"] and con.execute("SELECT 1 FROM managed_jobs WHERE task_id=? AND id=?",(row["task_id"],row["event_key"])).fetchone():
            result["job_id"]=row["event_key"]
        result["evidence_refs"]=payload.get("evidence_ids",[])
    elif item["source"]=="scene_read_events":
        result["job_id"]=row["read_id"]
    elif item["source"]=="managed_jobs":
        resolved=con.execute("SELECT payload_json FROM managed_events WHERE task_id=? AND kind='request_resolved' AND event_key=?",(row["task_id"],row["id"])).fetchone()
        if resolved:result["version"]=decode(resolved[0]).get("version")
    elif item["source"] in ("history_deployments","history_compilations") and row.get("policy_version_id"):
        version=con.execute("SELECT version FROM policy_versions WHERE id=? AND task_id=?",(row["policy_version_id"],row["task_id"])).fetchone()
        if version:result["version"]=version[0]
    elif item["source"]=="policy_versions":
        proposal=con.execute("SELECT p.job_id FROM bootstrap_versions b JOIN bootstrap_proposals p ON p.id=b.proposal_id WHERE b.policy_version_id=? AND p.task_id=?",(row["id"],row["task_id"])).fetchone()
        if proposal:result["job_id"]=proposal[0]
    # Standard task id must not inherit a source row id.
    result["task_id"]=row.get("task_id")
    result["storage_source"]=item["source"]
    result["action_source"]=detail.get("action_source","kernel" if item["source"]=="runtime_events" else "not_recorded")
    if with_detail:result["detail"]=detail
    else:result["detail"]=pick(detail,"decision","reason","error","user_request","meaning","result","name","target","operation","succeeded","call_id","domain_id","session_id","revision","temporary_grants","cleanup_status","cleanup_confirmed","change","base_version","confirmation","candidate_hash","hash","pid","action_source","classification","expected","effect_verified","before_hash","after_hash","verification_probe","native_sdk_verification","probe","probe_binding","kernel_events","kernel_event_ids","kernel","event_ids","authority","correlation")
    return safe(result)

def page(con,task_id,category="timeline",before=None,limit=50,with_detail=False,stage=None):
    if category not in CATEGORIES:raise HTTPException(422,"未知的档案事件分类")
    if stage not in (None,"preparation","execution","closure"):raise HTTPException(422,"未知的档案阶段")
    query=index(con);params={"task":task_id,"category":category,"limit":limit+1}
    predicate="category=:category"
    if stage:
        params["stage"]=stage
        predicate+=" AND stage=:stage"
    total=con.execute("SELECT count(*) FROM ("+query+") WHERE "+predicate,params).fetchone()[0]
    cursor_category=category+":"+stage if stage else category
    if before:
        params["time"],params["event_id"]=cursor_decode(before,task_id,cursor_category)
        predicate+=" AND (time<:time OR (time=:time AND id<:event_id))"
    rows=con.execute("SELECT * FROM ("+query+") WHERE "+predicate+" ORDER BY time DESC,id DESC LIMIT :limit",params).fetchall()
    items=[{**project(con,r,with_detail),"task_id":task_id} for r in rows[:limit]]
    return {"events":items,"total":total,"category":category,"stage":stage,"next_cursor":cursor_encode(task_id,cursor_category,rows[limit-1]) if len(rows)>limit else None,"history_only":True}

def header(con,task):
    managed=con.execute("SELECT state_json FROM managed_tasks WHERE task_id=?",(task["id"],)).fetchone()
    state=decode(managed[0]) if managed else {}
    ctx_row=con.execute("SELECT context_json FROM bootstrap_contexts WHERE task_id=?",(task["id"],)).fetchone()
    ctx=decode(ctx_row[0]) if ctx_row else {}
    source={"status":"not_recorded"}
    if {"workspace_task_sources","agent_workspaces"}<=tables(con):
        row=con.execute("SELECT s.workspace_id,s.manifest_hash,s.manifest_json,s.created_at,w.agent_id,w.path,w.origin FROM workspace_task_sources s JOIN agent_workspaces w ON s.workspace_id=w.id WHERE s.task_id=?",(task["id"],)).fetchone()
        if row:
            manifest=decode(row["manifest_json"])
            files=manifest.get("files",[]) if isinstance(manifest,dict) else manifest if isinstance(manifest,list) else []
            source={"status":"recorded",**pick(dict(row),"workspace_id","manifest_hash","agent_id","path","origin","created_at"),
                    "file_count":len(files),"files":[pick(x,"path","mapped_path","relative_path","sha256","content_hash","byte_size","size") for x in files if isinstance(x,dict)]}
    registered=ctx.get("workspace_source",{})
    if source.get("status")=="recorded":
        source.update(pick(registered,"agent_id","path"))
        instance=registered.get("instance")
        source["instance"]={"status":"recorded",**pick(instance,"instance_id","kind","generation","pid","start_ticks","native_workspace_id","session_ids","observed_at")} if isinstance(instance,dict) else {"status":"not_recorded"}
    binding_history=[]
    load_receipts=[(decode(r["payload_json"]),r["occurred_at"]) for r in con.execute("SELECT payload_json,occurred_at FROM managed_events WHERE task_id=? AND kind='policy_active' ORDER BY id",(task["id"],))]
    for item in state.get("binding_history",[]):
        entry=pick(item,"domain_id","runner_pid","watch_pid","version","session_id","created_at","ended_at")
        match=next(((receipt,time) for receipt,time in reversed(load_receipts) if receipt.get("version")==entry.get("version") and receipt.get("binding",{}).get("domain_id")==entry.get("domain_id")),None)
        if match:
            receipt,time=match
            entry={**pick(receipt.get("binding",{}),"domain_id","runner_pid","watch_pid"),"created_at":time,**pick(receipt,"session_id"),**entry,"source":"managed_events.policy_active"}
        binding_history.append(entry)
    execution={"status":"recorded" if state.get("binding") else "not_recorded","instance_id":"managed:"+task["id"] if managed else None,"session_id":state.get("session_id"),"phase":state.get("phase"),"gate":state.get("gate"),"last_binding":pick(state.get("binding",{}),"domain_id","runner_pid","watch_pid"),"binding_history":binding_history,"observation":"historical_receipts; live_state_not_checked"}
    return safe({"name":task["name"],"status":task["status"],"goal":task["prompt"],"constraints":pick(ctx,"declared_constraints","execution_constraints","platform_constraints","accepted_task_constraints"),"workspace":task["workspace"],"output_dir":task["output_dir"],"repository":pick(task,"repo","repo_url","commit_sha","ref_requested"),"source":source,"execution":execution,"created_at":task["created_at"],"updated_at":task["updated_at"],"ended_at":task["ended_at"],"history_only":True})

def stage_preview(con,task_id,stage,query):
    """Critical receipts are selected across the task, independently of recent pages."""
    kinds=("workspace_scene_read","policy_active","deployment","launch_receipt","startup_confirmed","startup_rejected","policy_review","policy_approved","policy_rejected","change_review","change_apply_failed","failure","recovering","recovered","recovery","recovery_requested","recovery_reassessment","recovery_started","recovery_completed","session_resumed","session_recovered","closed","close_failed","closure_requested","cleanup_result","task_ended","deployment_ended","task_stopped","task_execution_finished","revocation")
    params={"task":task_id,"stage":stage,"limit":20}
    names=",".join("'"+k+"'" for k in kinds)
    predicate="stage=:stage AND category='timeline' AND kind IN ("+names+")"
    total=con.execute("SELECT COUNT(*) FROM ("+query+") WHERE "+predicate,params).fetchone()[0]
    # Frequent reviews/failures cannot hide persisted loads and final cleanup.
    priority="CASE WHEN kind IN ('policy_active','deployment','launch_receipt','closed','cleanup_result','task_ended','deployment_ended') THEN 0 ELSE 1 END"
    rows=con.execute("SELECT * FROM ("+query+") WHERE "+predicate+" ORDER BY "+priority+",time DESC,id DESC LIMIT :limit",params).fetchall()
    highlights=[{**project(con,row,True),"task_id":task_id} for row in sorted(rows,key=lambda r:(r["time"],r["id"]),reverse=True)]
    return {"events":page(con,task_id,"timeline",limit=3,stage=stage)["events"],"highlights":highlights,"highlight_total":total,"highlight_limit":20}

def archive(task_id,before=None,limit=50):
    with db.connect() as con:
        con.execute("BEGIN")
        task=require_task(con,task_id);query=index(con)
        groups=con.execute("SELECT stage,category,count(*) AS n FROM ("+query+") GROUP BY stage,category",{"task":task_id}).fetchall()
        counts={k:sum(r["n"] for r in groups if r["category"]==k) for k in CATEGORIES}
        stages=[{"id":s,"status":"recorded" if any(r["stage"]==s for r in groups) else "not_recorded","event_count":sum(r["n"] for r in groups if r["stage"]==s),"timeline_count":sum(r["n"] for r in groups if r["stage"]==s and r["category"]=="timeline"),"category_counts":{k:sum(r["n"] for r in groups if r["stage"]==s and r["category"]==k) for k in CATEGORIES}} for s in ("preparation","execution","closure")]
        missing=[]
        for label,table in (("startup_generation","history_jobs"),("startup_candidates","bootstrap_proposals"),("runtime_jobs","managed_jobs"),("policy_versions","policy_versions"),("load_receipts","history_deployments")):
            predicate="kind='task_bootstrap' AND json_extract(input_json,'$.task_id')=?" if table=="history_jobs" else "task_id=?"
            exists=con.execute("SELECT 1 FROM "+table+" WHERE "+predicate+" LIMIT 1",(task_id,)).fetchone()
            if label=="load_receipts":exists=exists or con.execute("SELECT 1 FROM managed_events WHERE task_id=? AND kind IN ('policy_active','launch_receipt') LIMIT 1",(task_id,)).fetchone()
            if not exists:missing.append(label)
        for label,kinds in (("startup_review",("startup_confirmed","startup_rejected")),("runtime_review",("change_review",)),("closure_receipt",("closed","cleanup_result"))):
            found=con.execute("SELECT 1 FROM managed_events WHERE task_id=? AND kind IN ("+",".join("?" for _ in kinds)+") LIMIT 1",(task_id,*kinds)).fetchone()
            if label=="startup_review":
                found=found or con.execute("SELECT 1 FROM policy_versions WHERE task_id=? AND approved_at IS NOT NULL LIMIT 1",(task_id,)).fetchone()
            if not found:missing.append(label)
        result=page(con,task_id,"timeline",before,limit)
        previews={s:stage_preview(con,task_id,s,query) for s in ("preparation","execution","closure")}
        return {**result,"stage_previews":previews,"task_id":task_id,"header":header(con,task),"stages":stages,"counts":counts,"missing":missing,"coverage":"persisted receipts only; missing data is not_recorded; tool outcomes, kernel denials and control gates have distinct meanings"}

def events(task_id,category="timeline",before=None,limit=50,stage=None):
    with db.connect() as con:
        con.execute("BEGIN")
        require_task(con,task_id)
        return page(con,task_id,category,before,limit,stage=stage)

def event_detail(task_id,event_id):
    with db.connect() as con:
        con.execute("BEGIN")
        require_task(con,task_id)
        row=con.execute("SELECT * FROM ("+index(con)+") WHERE id=:id LIMIT 1",{"task":task_id,"id":event_id}).fetchone()
        if not row:raise HTTPException(404,"事件不存在或不属于此任务")
        return {**project(con,row,True),"task_id":task_id}


def archive_index(q="",status="all",page_number=0,limit=12,console=False):
    """One row per persisted task; filtering and pagination happen in SQLite."""
    if status not in ("all","active","ended") or page_number<0 or not 1<=limit<=50:
        raise HTTPException(422,"无效的任务档案分页或状态")
    with db.connect() as con:
        con.execute("BEGIN")
        available=tables(con)
        joins=" LEFT JOIN managed_tasks m ON m.task_id=t.id LEFT JOIN bootstrap_contexts b ON b.task_id=t.id"
        source_agent="json_extract(b.context_json,'$.workspace_source.agent_id')"
        source_workspace="json_extract(b.context_json,'$.workspace_source.id')"
        source_path="json_extract(b.context_json,'$.workspace_source.path')"
        if {"workspace_task_sources","agent_workspaces"}<=available:
            joins+=" LEFT JOIN workspace_task_sources wts ON wts.task_id=t.id LEFT JOIN agent_workspaces w ON w.id=wts.workspace_id"
            source_agent="COALESCE("+source_agent+",w.agent_id)"
            source_workspace="COALESCE("+source_workspace+",wts.workspace_id)"
            source_path="COALESCE("+source_path+",w.path)"
        terminal=("t.ended_at IS NOT NULL OR t.status IN ('ended','completed','stopped','cancelled','canceled','closed')"
                  " OR json_extract(m.state_json,'$.phase')='ended'"
                  " OR EXISTS (SELECT 1 FROM managed_events e WHERE e.task_id=t.id AND e.kind='closed')")
        base=("SELECT t.id,t.name,t.status,COALESCE(json_extract(m.state_json,'$.phase'),t.status) AS phase,"
              "t.created_at,t.ended_at,t.updated_at,COALESCE(json_extract(m.state_json,'$.version'),t.active_version,0) AS version,"
              "t.workspace AS workspace_path,t.repo AS workspace_name,"
              +source_agent+" AS source_agent,"+source_workspace+" AS source_workspace,"+source_path+" AS source_path,"
              "CASE WHEN ("+terminal+") THEN 1 ELSE 0 END AS is_ended FROM tasks t"+joins)
        params={"limit":limit,"offset":page_number*limit}
        predicate="1=1"
        if console:predicate+=" AND id NOT IN (SELECT record_id FROM console_retained_records WHERE kind='task')"
        if status!="all":
            predicate+=" AND is_ended=:ended"
            params["ended"]=1 if status=="ended" else 0
        if q.strip():
            params["search"]="%"+q.strip().replace("\\","\\\\").replace("%","\\%").replace("_","\\_")+"%"
            predicate+=" AND (name LIKE :search ESCAPE '\\' OR id LIKE :search ESCAPE '\\' OR workspace_name LIKE :search ESCAPE '\\' OR workspace_path LIKE :search ESCAPE '\\' OR source_path LIKE :search ESCAPE '\\' OR source_agent LIKE :search ESCAPE '\\')"
        query="SELECT * FROM ("+base+") WHERE "+predicate
        total=con.execute("SELECT COUNT(*) FROM ("+query+")",params).fetchone()[0]
        rows=con.execute(query+" ORDER BY updated_at DESC,id DESC LIMIT :limit OFFSET :offset",params).fetchall()
        records=[]
        for row in rows:
            row=dict(row)
            records.append(safe({**pick(row,"id","name","status","phase","created_at","ended_at","updated_at","version"),
                "is_ended":bool(row["is_ended"]),"history_only":True,
                "source":{"status":"recorded" if row["source_workspace"] or row["source_agent"] else "not_recorded","agent_id":row["source_agent"],"workspace_id":row["source_workspace"],"path":row["source_path"]},
                "workspace":{"name":row["workspace_name"],"path":row["workspace_path"]}}))
        return {"records":records,"total":total,"page":page_number,"pages":max(1,(total+limit-1)//limit),"limit":limit,"history_only":True}

"""Authoritative Scope transitions: candidate != approved != installed != verified."""
import hashlib
import json
import threading
import uuid
from pathlib import Path
from .. import db
from ..broker_client import call as broker_call
from ..services.policy import make_dsl, quote_dsl, make_restrictive_delta
from .models import ChangeRequest, Proposal

_locks = {}
_locks_guard = threading.Lock()


def lock(task_id):
    with _locks_guard: return _locks.setdefault(task_id, threading.RLock())


def digest(value):
    raw = value if isinstance(value, str) else json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def event(con, task_id, source, key, payload):
    con.execute("INSERT OR IGNORE INTO scope_events(task_id,source,source_key,payload_json,occurred_at) VALUES(?,?,?,?,?)",
                (task_id, source, key, json.dumps(payload, ensure_ascii=False), db.now()))


def task_and_session(con, task_id):
    task = con.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    session = con.execute("SELECT * FROM scope_sessions WHERE task_id=?", (task_id,)).fetchone()
    if not task or not session: raise ValueError("任务未启用 ScopeManager")
    return dict(task), dict(session)


def active(con, session):
    row = con.execute("SELECT * FROM scope_snapshots WHERE id=?", (session["active_snapshot_id"],)).fetchone()
    return db.row_dict(row)


def render(task, directories, output, *, cold=False):
    """Only deterministic supported write/unlink templates; LLM supplies no DSL."""
    ws = str(Path(task["workspace"]).resolve())
    dirs = sorted(set(directories))
    if not set(dirs) <= {"backend", "frontend"}: raise ValueError("未登记的写入目录")
    extra = []
    extra += ["rule scope-control-assets:",
              f"  block write file {quote_dsl(ws)} if AGENT",
              f"  block unlink file {quote_dsl(ws)} if AGENT",
              f"  block write file {quote_dsl(ws + '/.actplane/**')} if AGENT",
              f"  block unlink file {quote_dsl(ws + '/.actplane/**')} if AGENT",
              f"  block write file {quote_dsl(ws + '/.actplane')} if AGENT",
              f"  block unlink file {quote_dsl(ws + '/.actplane')} if AGENT",
              f"  block write file {quote_dsl(ws + '/.git/**')} if AGENT",
              f"  block unlink file {quote_dsl(ws + '/.git/**')} if AGENT",
              f"  block write file {quote_dsl(ws + '/.git')} if AGENT",
              f"  block unlink file {quote_dsl(ws + '/.git')} if AGENT",
              '  because "Execution evidence and repository roots are controlled platform assets."']
    # Session storage stays writable, but the native tool gate and boot configuration
    # must not be rewritten by the task they control, including across a restart.
    home = str(Path(ws).parent / ".dsh")
    profile = home + "/profiles/headless"
    # DSH rewrites its generated empty cordis.yml at every boot. Protect the
    # actual code, manifest and input overlays while allowing that lifecycle file.
    trusted_runtime = [home, home + "/profiles", profile,
                       profile + "/node_modules", profile + "/node_modules/**",
                       profile + "/package.json", profile + "/cordis.patch.yml",
                       profile + "/pnpm-lock.yaml", home + "/cordis.patch.yml",
                       home + "/settings.yaml", home + "/.credentials.yaml"]
    extra += ["rule scope-trusted-runtime:"]
    for target in trusted_runtime:
        extra += [f"  block write file {quote_dsl(target)} if AGENT",
                  f"  block unlink file {quote_dsl(target)} if AGENT"]
    extra += ['  because "Native execution gates and boot configuration are immutable platform assets."']
    if not output:
        out = task["output_dir"]
        extra += ["rule scope-output-root:", f"  block write file {quote_dsl(out)} if AGENT",
                  f"  block unlink file {quote_dsl(out)} if AGENT", '  because "Output requires a separate reviewed grant."']
    # Explicit denial is additive; task defaults can change only via a new bundle.
    for directory in ("backend", "frontend", "tests", "config"):
        if directory not in dirs:
            target = ws + "/" + directory
            extra += [f"rule scope-deny-{directory}:",
                      f"  block write file {quote_dsl(target)} if AGENT",
                      f"  block write file {quote_dsl(target + '/**')} if AGENT",
                      f"  block unlink file {quote_dsl(target)} if AGENT",
                      f"  block unlink file {quote_dsl(target + '/**')} if AGENT",
                      '  because "This directory is outside the reviewed task write scope."']
    # Deny unregistered repository locations while leaving the approved directories.
    allowed = [ws + "/" + d + "/**" for d in dirs]
    # Restrictive disjunction uses separate unless targets only when one dir is allowed.
    # For two dirs deny every other fixture directory; the repository envelope is fixed.
    if len(allowed) <= 1:
        exception = f" unless target {quote_dsl(allowed[0])}" if allowed else ""
        extra += ["rule scope-repository-boundary:",
                  f"  block write file {quote_dsl(ws + '/**')} if AGENT{exception}",
                  f"  block unlink file {quote_dsl(ws + '/**')} if AGENT{exception}",
                  '  because "Repository writes require a reviewed directory grant."']
    dsl, yaml = make_dsl(ws, task["output_dir"], {"read_only": cold, "allow_task_output": output}, "\n".join(extra))
    return {"schema":"ScopeSnapshot/1","allowed_write_dirs": dirs, "allow_output": bool(output), "protected_dirs": ["tests", "config"],
            "expiry": "task_end", "operations": ["write", "unlink"], "trusted_runtime_paths": trusted_runtime,
            "dsl": dsl, "yaml": yaml,
            "bundle_hash": digest(yaml), "coverage": {"file_write_unlink": "requires_live_verification",
            "network_dynamic": "out_of_scope", "read_confinement": "not_claimed"},
            "baseline": {"schema":"BaselinePolicy/1","outside_task_write": "deny", "remote_publish": "deny", "generator_apply_authority": False,
                         "repository_default":"read_only; reviewed task grant may change it", "execution":"DSH headless; low-privilege task UID"}}


def get_scope(task_id):
    with db.connect() as con:
        task, session = task_and_session(con, task_id)
        current = active(con, session)
        deltas = [db.row_dict(r) for r in con.execute("SELECT * FROM scope_deltas WHERE task_id=? ORDER BY created_at DESC", (task_id,))]
        events = [db.row_dict(r) for r in con.execute("SELECT * FROM scope_events WHERE task_id=? ORDER BY id DESC LIMIT 150", (task_id,))]
        snapshots = [db.row_dict(r) for r in con.execute("SELECT * FROM scope_snapshots WHERE task_id=? ORDER BY revision DESC", (task_id,))]
        jobs = [db.row_dict(r) for r in con.execute("SELECT id,delta_id,status,error,created_at FROM scope_jobs WHERE task_id=? ORDER BY created_at DESC", (task_id,))]
    try: execution = broker_call({"action": "status", "task_id": task_id}, timeout=8)
    except Exception: execution = {"available": False, "status": "unavailable"}
    effective = bool(current and session["phase"] != "ended" and execution.get("status") == "running"
                     and execution.get("domain_id") == current["binding"]["domain_id"]
                     and session["gate"] != "failed")
    return {"task": {"id": task_id, "name": task["name"], "status": task["status"], "workspace": task["workspace"],
                     "output_dir": task["output_dir"], "commit": task["commit_sha"]},
            "session": session, "current": current, "deltas": deltas, "events": events, "snapshots": snapshots,
            "default_scope": render(task, [], False, cold=True), "jobs": jobs, "execution": execution, "effective": effective}


def assess(task_id, body: ChangeRequest, *, actor="用户"):
    with lock(task_id), db.connect() as con:
        con.execute("BEGIN IMMEDIATE")
        task, session = task_and_session(con, task_id)
        if session["phase"] == "ended": raise ValueError("任务已结束")
        if session["gate"] == "failed": raise ValueError("执行状态未确认；请结束此任务并重新创建，不能基于未知规则继续应用")
        previous = con.execute("SELECT * FROM scope_deltas WHERE task_id=? AND request_key=?", (task_id, body.request_key)).fetchone()
        if previous:
            if previous["input_hash"] != digest(body.model_dump()): raise ValueError("幂等键对应不同输入")
            return db.row_dict(previous)
        if body.expected_snapshot != session["active_snapshot_id"]: raise ValueError("Scope 快照已变化")
        if session["apply_id"]: raise ValueError("任务正在应用权限变化")
        if body.kind == "task_grant" and session["phase"] != "cold": raise ValueError("任务已启动")
        if body.kind == "task_grant" and actor != "用户": raise ValueError("启动授权只接受用户请求")
        if body.kind == "task_grant" and not session["active_snapshot_id"]: raise ValueError("先验证冷启动默认 Scope，再申请任务授权")
        if body.kind != "task_grant" and session["phase"] not in ("running", "waiting_constraint"): raise ValueError("任务尚未运行")
        revision = session["message_revision"] + (actor == "用户")
        ident = uuid.uuid4().hex
        con.execute("INSERT INTO scope_deltas(id,task_id,kind,input_json,input_hash,base_snapshot_id,message_revision,process_epoch,request_key,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (ident, task_id, body.kind, json.dumps(body.model_dump(), ensure_ascii=False), digest(body.model_dump()),
                     session["active_snapshot_id"], revision, session["process_epoch"], body.request_key, db.now()))
        con.execute("UPDATE scope_sessions SET message_revision=? WHERE task_id=?", (revision, task_id))
        if body.kind == "restrict":
            con.execute("UPDATE scope_sessions SET gate='waiting_constraint',phase='waiting_constraint' WHERE task_id=?", (task_id,))
        event(con, task_id, "user_message" if actor == "用户" else "agent_request", ident, {"id": ident, "kind": body.kind, "text": body.text, "revision": revision, "actor": actor})
        con.execute("INSERT INTO scope_jobs(id,delta_id,task_id,created_at) VALUES(?,?,?,?)", (uuid.uuid4().hex, ident, task_id, db.now()))
        return db.row_dict(con.execute("SELECT * FROM scope_deltas WHERE id=?", (ident,)).fetchone())


def context_for(con, delta):
    task, session = task_and_session(con, delta["task_id"])
    if session["active_snapshot_id"] != delta["base_snapshot_id"] or session["message_revision"] != delta["message_revision"] or session["process_epoch"] != delta["process_epoch"]:
        raise ValueError("stale: 分析绑定的 Scope、消息或进程已变化")
    current = active(con, session)
    sources = [db.row_dict(r) for r in con.execute("SELECT * FROM scope_events WHERE task_id=? AND source IN ('user_message','agent_request','asset_manifest','agent_report','kernel','tool_result','boundary_pause','boundary_context_delivery') ORDER BY id", (task["id"],))]
    request_source = next(s for s in sources if s["source_key"] == delta["id"])
    sources = sources[-60:]
    if request_source not in sources: sources = [request_source, *sources]
    evidence = []
    for source in sources:
        content = source["payload"]
        if source["source"] == "kernel":
            raw = content["event"]
            content = {k: raw.get(k) for k in ("domain_id", "pid", "ppid", "op", "target", "blocked")}
            content["rule"] = raw.get("rule", {}).get("name")
        evidence.append({"evidence_id": str(source["id"]), "source_key": source["source_key"],
                         "source": source["source"], "content": content})
    if current:
        current = {k: current[k] for k in ("id", "revision", "content_hash", "payload")}
    return {"schema":"TaskContext/1","task_id": task["id"], "task": task["prompt"], "fixed_repository":task["repo"],
            "fixed_commit": task["commit_sha"],
            "expected_artifacts":{"report":task["output_dir"]+"/report.md"},
            "change": json.loads(delta["input_json"]), "base_snapshot": current, "sources": evidence,
            "request_evidence_id": next(e["evidence_id"] for e in evidence if e["source_key"] == delta["id"]),
            "requested_message_revision": delta["message_revision"], "process_epoch": delta["process_epoch"],
            "capabilities": {"write_unlink_dirs": ["backend", "frontend"], "output_expansion": "reviewed_restart",
                             "arbitrary_dsl": False, "semantic": "guidance_only"},
            "history": {"approved_only": True, "automatic_promotion": False}}


def validate_proposal(con, delta, draft):
    p = Proposal.model_validate(draft)
    task, session = task_and_session(con, delta["task_id"])
    if session["active_snapshot_id"] != delta["base_snapshot_id"] or session["process_epoch"] != delta["process_epoch"] or session["message_revision"] != delta["message_revision"]:
        raise ValueError("stale: 输入快照、消息或进程已变化")
    job = con.execute("SELECT result_json FROM scope_jobs WHERE delta_id=?", (delta["id"],)).fetchone()
    frozen = json.loads(job["result_json"]).get("context") if job else None
    ctx = frozen or context_for(con, delta)
    valid_ids = {s["evidence_id"] for s in ctx["sources"]}
    if not set(p.evidence_ids) <= valid_ids: raise ValueError("候选引用未登记证据；可引用 evidence_id=" + ",".join(sorted(valid_ids)) + "；本次要求=" + ctx["request_evidence_id"])
    # The authenticated request must be cited, not merely an unrelated asset.
    source = next(s for s in ctx["sources"] if s["source_key"] == delta["id"])
    if source["evidence_id"] not in p.evidence_ids: raise ValueError("必须引用本次变更来源 evidence_id=" + source["evidence_id"])
    old = (ctx["base_snapshot"] or {}).get("payload", {"allowed_write_dirs": [], "allow_output": False})
    if p.decision == "task_grant":
        if delta["kind"] != "task_grant" or set(p.allowed_write_dirs) != {"backend", "frontend"} or p.allow_output: raise ValueError("启动授权必须精确绑定登记任务目录")
    elif p.decision == "restrict":
        if delta["kind"] != "restrict" or set(p.allowed_write_dirs) != {"backend"} or p.allow_output != old["allow_output"]: raise ValueError("本演示收紧仅允许 backend，不能暗中扩权")
    elif p.decision == "expand":
        if delta["kind"] != "expand" or set(p.allowed_write_dirs) != set(old["allowed_write_dirs"]) or not p.allow_output: raise ValueError("扩权只能增加 output 并保留现有限制")
    elif p.decision in ("guidance_only", "no_change"):
        if set(p.allowed_write_dirs) != set(old["allowed_write_dirs"]) or p.allow_output != old["allow_output"]: raise ValueError("指导或无需变化不能改变权限")
    payload = render(task, p.allowed_write_dirs, p.allow_output)
    result = {"schema":"ScopeDelta/1","proposal": p.model_dump(), "effective": payload, "base_snapshot_id": delta["base_snapshot_id"],
              "message_revision": delta["message_revision"], "process_epoch": delta["process_epoch"]}
    from ..main import compile_policy
    state, diagnostics, error = compile_policy(payload["yaml"], task["id"], 900 + delta["message_revision"])
    if state != "compiled": raise ValueError("候选编译或支持能力失败：" + str(error))
    result["compile"] = diagnostics
    return result


def store_proposal(con, delta, draft):
    result = validate_proposal(con, delta, draft)
    if delta["proposal_hash"]: raise ValueError("已提交候选不可覆盖")
    con.execute("UPDATE scope_deltas SET proposal_json=?,proposal_hash=?,compile_status='compiled' WHERE id=?",
                (json.dumps(result, ensure_ascii=False), digest(result), delta["id"]))
    event(con, delta["task_id"], "candidate", delta["id"], {"delta_id": delta["id"], "decision": result["proposal"]["decision"], "explanation": result["proposal"]["explanation"]})
    return {"proposal_hash": digest(result)}


def confirm(task, session, payload, receipt, verification):
    binding = broker_call({"action": "status", "task_id": task["id"]}, timeout=8)
    if binding.get("domain_id") != receipt.get("domain_id") or binding.get("runner_pid") != receipt.get("runner_pid") or binding.get("status") != "running":
        raise ValueError("进程域绑定未确认")
    if not verification.get("passed") or verification.get("domain_id") != receipt["domain_id"]:
        raise ValueError("实际文件权限探针未通过")
    with db.connect() as con:
        row = con.execute("SELECT active_snapshot_id,apply_id FROM scope_sessions WHERE task_id=?", (task["id"],)).fetchone()
        if row["active_snapshot_id"] != session["active_snapshot_id"] or row["apply_id"] != session["apply_id"]:
            raise ValueError("确认期间基础 Scope 或应用归属改变")
        number = con.execute("SELECT COALESCE(MAX(revision),-1)+1 FROM scope_snapshots WHERE task_id=?", (task["id"],)).fetchone()[0]
        ident, epoch = uuid.uuid4().hex, digest({"domain": receipt["domain_id"], "runner": receipt["runner_pid"]})
        con.execute("INSERT INTO scope_snapshots VALUES(?,?,?,?,?,?,?,?,?)",
                    (ident, task["id"], number, session["active_snapshot_id"], json.dumps(payload, ensure_ascii=False), digest(payload),
                     json.dumps({**receipt, "process_epoch": epoch}), json.dumps(verification), db.now()))
        con.execute("UPDATE scope_sessions SET active_snapshot_id=?,process_epoch=? WHERE task_id=?", (ident, epoch, task["id"]))
        event(con, task["id"], "confirmed", ident, {"snapshot_id": ident, "revision": number, "bundle_hash": payload["bundle_hash"], "domain_id": receipt["domain_id"], "process_epoch": epoch})
    return ident


def checkpoint(task_id):
    with db.connect() as con:
        task, session = task_and_session(con, task_id)
        messages = [db.row_dict(r) for r in con.execute("SELECT * FROM scope_events WHERE task_id=? AND source IN ('user_message','agent_request','agent_report','tool_result') ORDER BY id", (task_id,))]
    root = Path(task["workspace"])
    hashes = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob("*.py") if p.is_file() and not p.is_symlink()}
    current = get_scope(task_id)["current"]
    value = {"schema": "PublicTaskCheckpoint/1", "task_id": task_id, "original_task": task["prompt"],
             "current_scope": {k: current[k] for k in ("id", "revision", "content_hash")},
             "confirmed_permissions": {"dirs": current["payload"]["allowed_write_dirs"], "output": current["payload"]["allow_output"]},
             "messages_and_results": messages[-15:], "workspace_python_hashes": hashes,
             "private_reasoning": "not_collected"}
    with db.connect() as con: event(con, task_id, "checkpoint", digest(value), value)
    return value


def launch_scope(task, payload, version, prompt, *, cold=False):
    from ..main import issue_task_token, revoke_task_tokens
    token, credential = issue_task_token(task["id"])
    try:
        result = broker_call({"action": "launch", "task_id": task["id"], "version": version, "workspace": task["workspace"],
                             "output_dir": task["output_dir"], "prompt": prompt, "dsl_text": payload["dsl"], "policy_yaml": payload["yaml"],
                             "task_token": token, "agentscope_url": __import__("agentscope_app.config", fromlist=["PUBLIC_BASE_URL"]).PUBLIC_BASE_URL,
                             "scope_mode": "cold" if cold else "managed"}, timeout=45)
        revoke_task_tokens(task["id"], credential)
        return result
    except Exception:
        from ..main import revoke_task_token
        revoke_task_token(credential)
        raise


def cold_start(task_id):
    with lock(task_id):
        with db.connect() as con:
            task, session = task_and_session(con, task_id)
            if session["gate"]=="failed" or session["phase"]=="ended": raise ValueError("当前执行状态禁止继续应用变更")
            if session["active_snapshot_id"]: return get_scope(task_id)
        payload = render(task, [], False, cold=True)
        receipt = launch_scope(task, payload, 100, "Cold baseline verification", cold=True)
        try:
            verification = broker_call({"action": "scope-verify", "task_id": task_id, "domain_id": receipt["domain_id"], "allowed_write_dirs": [], "allow_output": False}, timeout=35)
            confirm(task, session, payload, receipt, verification)
            with db.connect() as con: con.execute("UPDATE tasks SET active_domain_id=?,active_pid=?,watch_pid=? WHERE id=?", (receipt["domain_id"], receipt["runner_pid"], receipt["watch_pid"], task_id))
        except Exception:
            broker_call({"action": "stop", "task_id": task_id}, timeout=15)
            raise
        return get_scope(task_id)


def review_and_apply(task_id, delta_id, body):
    with lock(task_id):
        with db.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            task, session = task_and_session(con, task_id)
            if session["gate"]=="failed" or session["phase"]=="ended": raise ValueError("当前执行状态禁止继续应用变更")
            delta = con.execute("SELECT * FROM scope_deltas WHERE id=? AND task_id=?", (delta_id, task_id)).fetchone()
            if not delta: raise ValueError("变更不存在")
            delta = dict(delta)
            if delta["review_status"] != "pending": raise ValueError("变更已审核")
            if delta["proposal_hash"] != body.expected_proposal_hash or not delta["proposal_json"]: raise ValueError("审批必须绑定候选 hash")
            data = json.loads(delta["proposal_json"])
            if digest(data) != delta["proposal_hash"]: raise ValueError("候选内容漂移")
            validate_proposal(con, delta, data["proposal"])
            if con.execute("SELECT 1 FROM scope_jobs WHERE delta_id=? AND status!='completed'", (delta_id,)).fetchone(): raise ValueError("Pi 尚未完成")
            if body.decision == "reject":
                con.execute("UPDATE scope_deltas SET review_status='rejected',reviewed_by=? WHERE id=?", (body.reviewed_by, delta_id))
                event(con, task_id, "review", delta_id, {"decision": "rejected", "user_requirement_remains": delta["kind"] == "restrict"})
                con.commit()
                return get_scope(task_id)
            if session["phase"] == "waiting_constraint" and data["proposal"]["decision"] in ("task_grant", "expand"):
                raise ValueError("先落实仍待处理的用户收紧要求，不能通过其他授权重新开放工具门")
            if session["apply_id"]: raise ValueError("已有应用作业")
            con.execute("UPDATE scope_deltas SET review_status='approved',reviewed_by=?,apply_status='applying' WHERE id=?", (body.reviewed_by, delta_id))
            con.execute("UPDATE scope_sessions SET apply_id=?,gate='applying' WHERE task_id=?", (delta_id, task_id))
            event(con, task_id, "review", delta_id, {"decision":"approved","reviewed_by":body.reviewed_by,
                "proposal_hash":delta["proposal_hash"],"base_snapshot_id":delta["base_snapshot_id"],
                "message_revision":delta["message_revision"],"process_epoch":delta["process_epoch"]})
            session["apply_id"] = delta_id
        installed = False
        try:
            decision, payload = data["proposal"]["decision"], data["effective"]
            if decision in ("guidance_only", "no_change"):
                with db.connect() as con:
                    con.execute("UPDATE scope_deltas SET apply_status='not_required',verify_status='not_required' WHERE id=?", (delta_id,))
                    waiting = delta["kind"] == "restrict" or session["phase"] == "waiting_constraint"
                    con.execute("UPDATE scope_sessions SET apply_id=NULL,gate=? WHERE task_id=?", ("waiting_constraint" if waiting else "open", task_id))
                return get_scope(task_id)
            old = get_scope(task_id)["current"]
            payload = {**payload, "scope_lineage":[*(old["payload"].get("scope_lineage", [])),
                {"delta_id":delta_id,"decision":decision,"base_snapshot_id":old["id"]}]}
            number = 100 + old["revision"] + 1
            if decision == "restrict":
                added = make_restrictive_delta(task, {"id": delta_id, "path": str(Path(task["workspace"]) / "backend"),
                                                    "justification": "Reviewed backend-only task restriction."})
                receipt = broker_call({"action": "restrict", "task_id": task_id, "request_id": delta_id, "domain_id": old["binding"]["domain_id"],
                                       "delta_text": added, "approved_by": body.reviewed_by, "approval_ref": delta_id}, timeout=32)
                receipt.update(runner_pid=old["binding"]["runner_pid"], watch_pid=old["binding"].get("watch_pid"))
                installed = True
                # Exact effective combination includes installed base plus appended delta.
                payload = {**payload, "dsl": old["payload"]["dsl"] + "\n" + added, "applied_deltas": [*(old["payload"].get("applied_deltas", [])), delta_id]}
                payload["yaml"] = "version: 1\nfeedback:\n  path: " + json.dumps(task["workspace"] + "/.actplane/last-violation.txt") + "\npolicy: |\n" + "\n".join("  " + s for s in payload["dsl"].splitlines()) + "\n"
                payload["bundle_hash"] = digest(payload["yaml"])
            else:
                saved = checkpoint(task_id)
                broker_call({"action": "stop", "task_id": task_id}, timeout=15)
                from ..main import revoke_task_tokens
                revoke_task_tokens(task_id)
                prompt = task["prompt"] + "\n工作区：" + task["workspace"] + "\n[公开任务检查点]\n" + json.dumps(saved, ensure_ascii=False)
                if len(prompt) > 8000: raise ValueError("公开检查点超过 DSH 输入上限；不能截断用户要求")
                receipt = launch_scope(task, payload, number, prompt)
                installed = True
            verification = broker_call({"action": "scope-verify", "task_id": task_id, "domain_id": receipt["domain_id"],
                                        "allowed_write_dirs": payload["allowed_write_dirs"], "allow_output": payload["allow_output"]}, timeout=35)
            ident = confirm(task, session, payload, receipt, verification)
            with db.connect() as con:
                con.execute("UPDATE scope_deltas SET apply_status='loaded',verify_status='confirmed',receipt_json=? WHERE id=?", (json.dumps({"receipt": receipt, "verification": verification, "snapshot_id": ident}), delta_id))
                con.execute("UPDATE scope_sessions SET apply_id=NULL,phase='running',gate='open' WHERE task_id=?", (task_id,))
                con.execute("UPDATE tasks SET status='running',active_domain_id=?,active_pid=?,watch_pid=?,updated_at=? WHERE id=?", (receipt["domain_id"], receipt["runner_pid"], receipt["watch_pid"], db.now(), task_id))
            return get_scope(task_id)
        except Exception as error:
            # Installed-but-unverified restrictions cannot safely be undone. Halt execution.
            try: state = broker_call({"action": "status", "task_id": task_id}, timeout=8)
            except Exception: state = {"available": False}
            if installed or not state.get("available"):
                try: broker_call({"action": "stop", "task_id": task_id}, timeout=15)
                except Exception: pass
                from ..main import revoke_task_tokens
                revoke_task_tokens(task_id)
            with db.connect() as con:
                con.execute("UPDATE scope_deltas SET apply_status=?,verify_status='failed',receipt_json=? WHERE id=?",
                    ("loaded_unverified" if installed else "failed",json.dumps({"error":str(error),"installed":installed,"observed_binding":state}),delta_id))
                con.execute("UPDATE scope_sessions SET apply_id=NULL,gate='failed',phase='waiting_constraint' WHERE task_id=?", (task_id,))
                event(con, task_id, "apply_failure", delta_id, {"error": str(error), "installed": installed})
            raise


def close_task(task_id):
    with lock(task_id):
        with db.connect() as con:
            task, session = task_and_session(con, task_id)
            if session["phase"]=="ended": return get_scope(task_id)
            con.execute("UPDATE scope_sessions SET gate='closed' WHERE task_id=?", (task_id,))
        result = broker_call({"action": "stop", "task_id": task_id}, timeout=15)
        if result.get("status") not in ("stopped", "not_running"): raise ValueError("结束清理未确认")
        from ..main import revoke_task_tokens
        revoke_task_tokens(task_id)
        with db.connect() as con:
            con.execute("UPDATE scope_sessions SET phase='ended',process_epoch=NULL WHERE task_id=?", (task_id,))
            con.execute("UPDATE tasks SET status='completed',active_pid=NULL,active_domain_id=NULL,watch_pid=NULL,ended_at=?,updated_at=? WHERE id=?", (db.now(), db.now(), task_id))
            con.execute("UPDATE scope_jobs SET status='interrupted',token_hash=NULL WHERE task_id=? AND status IN ('queued','running')", (task_id,))
            con.execute("UPDATE scope_deltas SET review_status='expired' WHERE task_id=? AND review_status='pending'", (task_id,))
            event(con, task_id, "ended", "close", {"cleanup": result, "temporary_grants": "revoked"})
        return get_scope(task_id)

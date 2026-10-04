"""One load-eligibility contract for UI, bundle construction and Provider revalidation."""
import json
import hashlib
import os
from pathlib import Path
from .. import db


def environment_binding(ctx):
    from .pipeline import digest
    from .capabilities import translation_capabilities
    with db.connect() as con:
        row = con.execute("SELECT * FROM tasks WHERE id=?", (ctx.get("task_id"),)).fetchone()
    if not row: raise ValueError("适配任务不存在")
    task = dict(row)
    from ..config import DSH_BIN, DSH_HOME, ACTPLANE_BIN
    runtime_files=[DSH_BIN,ACTPLANE_BIN]
    runtime={str(p):hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None for p in runtime_files}
    if DSH_BIN.is_file():
        from ..broker_client import call
        runtime['effective_dsh']=call({'action':'dsh-config-facts'},timeout=8)
    value = {"task_id":task["id"],"repository":task["repo"],"commit":task["commit_sha"],
        "workspace":task["workspace"],"output_dir":task["output_dir"],"profile":task["dsh_profile"],
        "capabilities":translation_capabilities(),"runtime_hashes":runtime}
    return {"values":value,"hash":digest(value)}


def blockers(data, statement, *, task=None):
    metadata = data.get("policy_record", {}).get("metadata", {})
    reasons = []
    from .pipeline import reviewed_phrase_errors
    reasons.extend(reviewed_phrase_errors(statement.get('statement',{})))
    adaptation = metadata.get("adaptation", {})
    if adaptation.get("state") == "required": reasons.append("需本机适配")
    if adaptation and adaptation.get("required_parameters"): reasons.append("存在未绑定参数")
    completeness = metadata.get("completeness", {}).get("status")
    if completeness and completeness != "complete": reasons.append("完整性二审未通过")
    ctx = statement.get("resolved_context", {})
    if data.get("policy_ir"):
        from ..policy_ir import PolicyIR, render
        from .pipeline import digest
        ir = PolicyIR.model_validate(data["policy_ir"])
        if ir.required_context or ir.unresolved: reasons.append("IR 执行缺口未解决")
        try:
            from .models import StrategyStatementVersion
            from .pipeline import validate_ir_scope
            if data.get("actplane_dsl"):validate_ir_scope(ir,StrategyStatementVersion.model_validate(statement))
            expected = render(ir, "h_" + data["statement_version_id"].replace("-", "")[:16] + "_")
            if expected != data.get("actplane_dsl"): reasons.append("IR 与 DSL 不一致")
        except ValueError as e: reasons.append("IR 无效："+str(e))
        env = metadata.get("environment")
        if data.get("actplane_dsl"):
            if not env or not ctx.get("task_id"): reasons.append("没有服务端适配凭据")
            else:
                try: current = environment_binding(ctx)
                except (ValueError,RuntimeError,OSError): reasons.append("无法核验适配任务环境");return reasons
                if current != env: reasons.append("任务环境已变化，需重新适配")
                if ctx.get("environment_binding") != current: reasons.append("适配版本未绑定当前环境")
                if task is not None and task["id"] != ctx["task_id"]: reasons.append("DSL 已绑定其他任务")
            if metadata.get("evidence", {}).get("unresolved"): reasons.append("证据或参数缺口未解决")
    return list(dict.fromkeys(reasons))

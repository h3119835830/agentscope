import json
import uuid
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from .. import db
from ..history import jobs
from .models import VersionRequest
from .scene import CASES, context, create_scene, digest
from .tools import invoke, revoke
from .validation import validate, verify_version

router = APIRouter()

def bad_request(error):
    return HTTPException(409, str(error))

def handoff(con, task_id):
    task=con.execute('SELECT * FROM tasks WHERE id=?',(task_id,)).fetchone()
    version=con.execute("SELECT * FROM policy_versions WHERE task_id=? AND version=? AND status='approved'",(task_id,task['active_version'])).fetchone()
    if not version:return None
    link=verify_version(con,task_id,version['id'])
    deployment=con.execute('SELECT * FROM history_deployments WHERE task_id=? AND policy_version_id=? ORDER BY created_at DESC LIMIT 1',(task_id,version['id'])).fetchone()
    receipt=json.loads(deployment['receipt_json'] or '{}') if deployment else None
    return {'task_context':context(task_id,con),'approved_version':{'id':version['id'],'version':version['version'],
            'context_hash':link['context_hash'],'proposal_hash':link['proposal_hash'],'bundle_hash':digest(version['policy_yaml'])},
            'binding_receipt':receipt,'event_baseline':receipt.get('event_baseline',{'count':0,'basis':'fresh task creation before its first domain'}) if receipt else None,
            'runtime_governance_enabled':False}

@router.get("/api/rq5/scenarios")
def scenarios():
    return {"scenarios": CASES, "label": "RQ5 场景迁移至 AgentScope/DSH 的扩展验收", "test_library": "isolated instance only"}

@router.post("/api/rq5/scenarios/{scenario_id}/tasks")
def create(scenario_id: str):
    try: return create_scene(scenario_id)
    except ValueError as error: raise bad_request(error)

@router.post("/api/tasks/{task_id}/bootstrap")
def bootstrap(task_id: str):
    try: context(task_id)
    except ValueError as error: raise bad_request(error)
    with db.connect() as con:
        task = con.execute("SELECT status FROM tasks WHERE id=?", (task_id,)).fetchone()
        if task["status"] == "bootstrapping":
            job = con.execute("SELECT id,status FROM history_jobs WHERE kind='task_bootstrap' AND json_extract(input_json,'$.task_id')=? AND status IN ('queued','running') ORDER BY created_at DESC LIMIT 1", (task_id,)).fetchone()
            if job: return dict(job)
        if task["status"] not in ("prepared", "policy_review", "approved"): raise HTTPException(409, "task cannot generate startup policy now")
        if not con.execute("UPDATE tasks SET status='bootstrapping',updated_at=? WHERE id=? AND status=?", (db.now(), task_id, task["status"])).rowcount:
            raise HTTPException(409, "task generation already claimed")
    try: return jobs.enqueue("task_bootstrap", {"task_id": task_id})
    except Exception:
        with db.connect() as con: con.execute("UPDATE tasks SET status=? WHERE id=? AND status='bootstrapping'", (task["status"], task_id))
        raise

@router.get("/api/tasks/{task_id}/bootstrap")
def state(task_id: str):
    try: ctx = context(task_id)
    except ValueError as error: raise bad_request(error)
    with db.connect() as con:
        job_rows = [db.row_dict(r) for r in con.execute("SELECT * FROM history_jobs WHERE kind='task_bootstrap' AND json_extract(input_json,'$.task_id')=? ORDER BY created_at DESC", (task_id,))]
        proposals = [db.row_dict(r) for r in con.execute("SELECT * FROM bootstrap_proposals WHERE task_id=? ORDER BY created_at DESC", (task_id,))]
        versions = [dict(r) for r in con.execute("SELECT b.*,v.version,v.status,v.compile_state FROM bootstrap_versions b JOIN policy_versions v ON v.id=b.policy_version_id WHERE v.task_id=? ORDER BY v.version DESC", (task_id,))]
        result = con.execute("SELECT result_json FROM bootstrap_results WHERE task_id=?", (task_id,)).fetchone()
        events = [db.row_dict(r) for r in con.execute("SELECT e.* FROM bootstrap_tool_events e JOIN history_jobs j ON j.id=e.job_id WHERE json_extract(j.input_json,'$.task_id')=? ORDER BY e.occurred_at", (task_id,))]
        try:startup_handoff=handoff(con,task_id)
        except ValueError as error:startup_handoff={'diagnostic':str(error)}
    return {"context": ctx, "jobs": job_rows, "proposals": proposals, "versions": versions,
            "tool_events": events, "acceptance": json.loads(result[0]) if result else None,'handoff':startup_handoff}

@router.get('/api/tasks/{task_id}/bootstrap/handoff')
def read_handoff(task_id:str):
    try:
        context(task_id)
        with db.connect() as con:return handoff(con,task_id)
    except ValueError as error:raise bad_request(error)

@router.post("/api/tasks/{task_id}/bootstrap/jobs/{job_id}/cancel")
def cancel(task_id: str, job_id: str):
    with db.connect() as con:
        changed = con.execute("UPDATE history_jobs SET status='interrupted',error='cancelled by administrator',finished_at=? WHERE id=? AND kind='task_bootstrap' AND json_extract(input_json,'$.task_id')=? AND status IN ('queued','running')", (db.now(), job_id, task_id)).rowcount
        if not changed: raise HTTPException(409, "job is not cancellable")
        con.execute("UPDATE tasks SET status='prepared' WHERE id=? AND status='bootstrapping'", (task_id,))
    revoke(job_id)
    return {"status": "interrupted"}

@router.post("/api/tasks/{task_id}/bootstrap/proposals/{proposal_id}/versions")
def version(task_id: str, proposal_id: str, body: VersionRequest):
    from ..main import create_policy_version
    with db.connect() as con:
        task = con.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        proposal = con.execute("SELECT * FROM bootstrap_proposals WHERE id=? AND task_id=?", (proposal_id, task_id)).fetchone()
        if not task or not proposal: raise HTTPException(404, "proposal/task missing")
        if proposal['state'] != 'validated':raise HTTPException(409,'proposal needs clarification; execution gaps block loading package construction')
        origin_job=proposal["job_id"].removeprefix("derived:")
        job=con.execute("SELECT status FROM history_jobs WHERE id=?",(origin_job,)).fetchone()
        if not job or job["status"]!="completed":raise HTTPException(409,"generation job has not completed successfully")
        if task["status"] not in ("prepared", "policy_review", "approved"): raise HTTPException(409, "cannot build another startup version")
        existing = con.execute("SELECT v.id,v.version,v.compile_state FROM bootstrap_versions b JOIN policy_versions v ON v.id=b.policy_version_id WHERE b.proposal_id=? AND b.condition=?", (proposal_id, body.condition)).fetchone()
        if existing: return dict(existing)
        changed = con.execute("UPDATE tasks SET status='policy_generating' WHERE id=? AND status=?", (task_id, task["status"])).rowcount
        if not changed: raise HTTPException(409, "version generation already claimed")
        number = con.execute("SELECT COALESCE(MAX(version),0)+1 FROM policy_versions WHERE task_id=?", (task_id,)).fetchone()[0]
    task = dict(task)
    try:
        data = json.loads(proposal["proposal_json"])
        if digest(data) != proposal["content_hash"]: raise ValueError("proposal content hash mismatch")
        checked = validate(task_id, data["draft"])
        if not checked["valid"] or checked["proposal_hash"] != proposal["content_hash"]: raise ValueError("candidate no longer validates")
        ctx = context(task_id)
        extra = data["actplane_dsl"] if body.condition == "B" else ""
        prompt = ctx["environment"] + "\n[Approved platform constraints]\n" + ctx["platform_constraints"] + "\n\n" + task["prompt"] + "\n\n[Approved task guidance]\n" + "\n".join(data["guidance"])
        if len(prompt) > 8000: raise ValueError("approved prompt exceeds DSH limit")
        result = create_policy_version(task, number, "task_bootstrap", ctx["base_settings"], [], data["draft"]["summary"], extra_rules=extra)
        with db.connect() as con:
            con.execute("INSERT INTO bootstrap_versions VALUES(?,?,?,?,?,?,?)", (result["id"], proposal_id, ctx["context_hash"], proposal["content_hash"], body.condition, prompt, digest(prompt)))
            info = result["compile_result"]
            info["policy_ir"]["bootstrap"] = {"proposal_id": proposal_id, "proposal_hash": proposal["content_hash"], "context_hash": ctx["context_hash"], "condition": body.condition, "proposal": data, "prompt_hash": digest(prompt)}
            con.execute("UPDATE policy_versions SET compile_json=? WHERE id=?", (json.dumps(info), result["id"]))
            con.execute("UPDATE tasks SET status='policy_review' WHERE id=? AND status='policy_generating'", (task_id,))
        return result
    except Exception as error:
        with db.connect() as con: con.execute("UPDATE tasks SET status=? WHERE id=? AND status='policy_generating'", (task["status"], task_id))
        raise bad_request(error)

@router.post("/api/tasks/{task_id}/bootstrap/proposals/{proposal_id}/instantiate")
def instantiate(task_id: str, proposal_id: str):
    """A/B pairing reuses one Pi decision with deterministic path/evidence rebinding."""
    with db.connect() as con:
        row = con.execute("SELECT * FROM bootstrap_proposals WHERE id=? AND task_id=? AND state='validated'", (proposal_id, task_id)).fetchone()
        if not row: raise HTTPException(404, "validated source proposal missing")
        original = json.loads(row["proposal_json"])
        if digest(original) != row["content_hash"]: raise HTTPException(409, "source proposal changed")
        ctx = context(task_id, con)
        old_sources = {r["id"]: dict(r) for r in con.execute("SELECT * FROM bootstrap_sources WHERE task_id=?", (task_id,))}
    created = create_scene(ctx["scenario_id"])
    new_ctx = context(created["id"])
    with db.connect() as con:
        new_sources = [dict(r) for r in con.execute("SELECT * FROM bootstrap_sources WHERE task_id=?", (created["id"],))]
    by_origin = {(s["role"], s["path"].replace(new_ctx["workspace"], "<workspace>")): s for s in new_sources}
    draft = json.loads(json.dumps(original["draft"]))
    draft["context_hash"] = new_ctx["context_hash"]
    for atom in draft["atoms"]:
        atom["paths"] = [p.replace(ctx["workspace"], new_ctx["workspace"]) for p in atom["paths"]]
        atom["reason"] = atom["reason"].replace(ctx["workspace"], new_ctx["workspace"])
        atom["statement"] = atom["statement"].replace(ctx["workspace"], new_ctx["workspace"])
        atom["evidence_ids"] = [by_origin[(old_sources[sid]["role"], old_sources[sid]["path"].replace(ctx["workspace"], "<workspace>"))]["id"] for sid in atom["evidence_ids"]]
    draft["guidance"] = [g.replace(ctx["workspace"], new_ctx["workspace"]) for g in draft["guidance"]]
    draft["summary"] = draft["summary"].replace(ctx["workspace"], new_ctx["workspace"])
    try:
        result = validate(created["id"], draft)
        if not result["valid"]: raise ValueError("rebound candidate cannot compile")
        ident = uuid.uuid4().hex
        validation = {k:v for k,v in result.items() if k != "proposal"}
        validation["derivation"] = {"parent_task": task_id, "parent_proposal": proposal_id, "parent_hash": row["content_hash"], "method": "deterministic path/evidence rebinding; no additional model generation"}
        with db.connect() as con:
            con.execute("INSERT INTO bootstrap_proposals VALUES(?,?,?,?,?,?,?,?,?)", (ident, created["id"], "derived:" + row["job_id"], new_ctx["context_hash"], result["proposal_hash"], json.dumps(result["proposal"]), json.dumps(validation), "validated", db.now()))
            db.audit(con, created["id"], "bootstrap_proposal_instantiated", "administrator", validation["derivation"])
        return {**created, "proposal_id": ident, "proposal_hash": result["proposal_hash"]}
    except ValueError as error: raise bad_request(error)

@router.post("/api/generator/tasks/{task_id}/jobs/{job_id}/tools/{tool}")
def generator(task_id: str, job_id: str, tool: str, body: dict, request: Request):
    header = request.headers.get("authorization", "")
    token = header[7:] if header.lower().startswith("bearer ") else ""
    return invoke(task_id, job_id, tool, body, token)

def approved_prompt(task):
    with db.connect() as con:
        row = con.execute("SELECT id FROM policy_versions WHERE task_id=? AND version=?", (task["id"], task["active_version"])).fetchone()
        if not row: return None
        link = verify_version(con, task["id"], row["id"])
    return link["prompt_text"] if link else None

import json
import secrets
import time
import uuid
from fastapi import HTTPException
from .. import db
from .scene import context, digest
from .library import search
from .validation import CAPABILITIES, validate

TOOLS = ("get_task_context", "list_policy_sources", "read_policy_source", "search_historical_policies",
         "get_enforcement_capabilities", "validate_policy_draft", "submit_task_policy_proposal")

def issue(task_id, job_id):
    token = secrets.token_urlsafe(36)
    with db.connect() as con:
        con.execute("INSERT INTO bootstrap_credentials(id,task_id,job_id,token_hash,expires_at) VALUES(?,?,?,?,?)",
                    (uuid.uuid4().hex, task_id, job_id, digest(token), time.time() + 180))
    return token

def revoke(job_id):
    with db.connect() as con: con.execute("UPDATE bootstrap_credentials SET revoked_at=? WHERE job_id=? AND revoked_at IS NULL", (db.now(), job_id))

def invoke(task_id, job_id, tool, args, token):
    if tool not in TOOLS: raise HTTPException(404, "generator tool not allowed")
    with db.connect() as con:
        credential = con.execute("SELECT * FROM bootstrap_credentials WHERE task_id=? AND job_id=? AND token_hash=? AND revoked_at IS NULL AND expires_at>?", (task_id, job_id, digest(token), time.time())).fetchone()
        if not credential: raise HTTPException(401, "invalid or expired generation credential")
        changed = con.execute("UPDATE bootstrap_credentials SET calls=calls+1 WHERE id=? AND calls<40", (credential["id"],)).rowcount
        if not changed: raise HTTPException(429, "generation tool budget exhausted")
        job = con.execute("SELECT status FROM history_jobs WHERE id=? AND kind='task_bootstrap'", (job_id,)).fetchone()
        if not job or job["status"] != "running": raise HTTPException(409, "generation job is not running")
    try:
        result = execute(task_id, job_id, tool, args)
    except (ValueError, KeyError) as error:
        result = {"valid": False, "diagnostic": str(error)[:2000]}
    with db.connect() as con:
        con.execute("INSERT INTO bootstrap_tool_events VALUES(?,?,?,?,?,?)", (uuid.uuid4().hex, job_id, tool, json.dumps(args), json.dumps(result), db.now()))
    return result

def execute(task_id, job_id, tool, args):
    allowed = {"get_task_context": set(), "list_policy_sources": set(), "get_enforcement_capabilities": set(),
               "read_policy_source": {"source_id"}, "search_historical_policies": {"query"},
               "validate_policy_draft": {"draft"}, "submit_task_policy_proposal": {"proposal_hash"}}
    if set(args) != allowed[tool]: raise ValueError("tool parameters must match schema exactly; expected keys="+json.dumps(sorted(allowed[tool]))+"; received keys="+json.dumps(sorted(args)))
    if tool == "get_task_context":
        ctx=context(task_id)
        with db.connect() as con:source=con.execute("SELECT id,text,content_hash FROM bootstrap_sources WHERE task_id=? AND role='task'",(task_id,)).fetchone()
        if not source or digest(source['text'])!=ctx['raw_prompt_hash'] or source['content_hash']!=ctx['raw_prompt_hash']:raise ValueError('task description hash mismatch')
        return {**ctx,'task_description':source['text'],'task_description_source_id':source['id']}
    if tool == "get_enforcement_capabilities": return CAPABILITIES
    if tool in ("list_policy_sources", "read_policy_source"):
        with db.connect() as con:
            if tool == "list_policy_sources":
                receipts={json.loads(r['input_json']).get('source_id'):json.loads(r['output_json']).get('content_hash') for r in con.execute("SELECT input_json,output_json FROM bootstrap_tool_events WHERE job_id=? AND tool='read_policy_source'",(job_id,)) if json.loads(r['output_json']).get('content_hash')}
                sources=[dict(r) for r in con.execute("SELECT id,role,path,content_hash,length(text) bytes FROM bootstrap_sources WHERE task_id=?", (task_id,))]
                return {"sources":[{**source,'read_receipt_verified':receipts.get(source['id'])==source['content_hash'],'required_before_validation':source['role'] in ('task','platform','environment','dsh_config')} for source in sources]}
            row = con.execute("SELECT * FROM bootstrap_sources WHERE task_id=? AND id=?", (task_id, args["source_id"])).fetchone()
        if not row: raise ValueError("source is not registered for this task")
        if digest(row["text"]) != row["content_hash"]: raise ValueError("source hash mismatch")
        return dict(row)
    if tool == "search_historical_policies":
        query = args["query"]
        if not isinstance(query, str) or not 1 <= len(query) <= 2000: raise ValueError("invalid retrieval query")
        return search(query)
    with db.connect() as con:
        events = [dict(r) for r in con.execute("SELECT * FROM bootstrap_tool_events WHERE job_id=?", (job_id,))]
    if tool == "validate_policy_draft":
        required = {"get_task_context", "list_policy_sources", "read_policy_source", "search_historical_policies", "get_enforcement_capabilities"}
        if not required.issubset({e["tool"] for e in events}):
            raise ValueError("understand the task, inspect evidence, retrieve history and query capabilities before validation")
        with db.connect() as con:core={r[0] for r in con.execute("SELECT id FROM bootstrap_sources WHERE task_id=? AND role IN ('task','platform','environment','dsh_config')",(task_id,))}
        read={json.loads(e['input_json']).get('source_id') for e in events if e['tool']=='read_policy_source' and json.loads(e['output_json']).get('content_hash')}
        if not core.issubset(read):raise ValueError('Unread required source IDs: '+json.dumps(sorted(core-read)))
        if not isinstance(args['draft'],dict):raise ValueError('draft must be a JSON object')
        cited={source for atom in args['draft'].get('atoms',[]) for source in atom.get('evidence_ids',[])}
        if not cited.issubset(read):raise ValueError('Unread referenced source IDs: '+json.dumps(sorted(cited-read))+'; obtain read_policy_source receipts before validating this draft')
        # Evidence completion is not a semantic draft repair. Only a candidate
        # with all referenced receipts consumes the initial/two-repair budget.
        with db.connect() as con:
            con.execute("INSERT OR IGNORE INTO bootstrap_validation_budget(job_id,calls) VALUES(?,0)",(job_id,))
            if not con.execute("UPDATE bootstrap_validation_budget SET calls=calls+1 WHERE job_id=? AND calls<3",(job_id,)).rowcount:
                raise HTTPException(429,'initial validation plus at most two repair rounds')
        result = validate(task_id, args["draft"])
        if result["valid"] or result["state"] == "needs_clarification":
            with db.connect() as con:
                con.execute("INSERT OR REPLACE INTO bootstrap_validations VALUES(?,?,?,?)", (job_id, result["proposal_hash"], task_id, json.dumps(result)))
        return result
    with db.connect() as con:
        saved = con.execute("SELECT result_json FROM bootstrap_validations WHERE job_id=? AND task_id=? AND proposal_hash=?", (job_id, task_id, args["proposal_hash"])).fetchone()
    if not saved: raise ValueError("no validated candidate with this hash for the current job")
    result = json.loads(saved[0])
    checked = validate(task_id, result["proposal"]["draft"])
    if checked["state"] not in ("validated","needs_clarification") or checked["proposal_hash"] != result["proposal_hash"]: raise ValueError("candidate no longer validates")
    required = {"get_task_context", "list_policy_sources", "read_policy_source", "search_historical_policies", "get_enforcement_capabilities", "validate_policy_draft"}
    if not required.issubset({e["tool"] for e in events}): raise ValueError("understand, inspect, retrieve and validate before submission")
    # Referenced evidence must actually have been returned to this job.
    read_ids = {json.loads(e["input_json"]).get("source_id") for e in events if e["tool"] == "read_policy_source" and json.loads(e["output_json"]).get("content_hash")}
    retrieved = {(m["id"], m["hash"]) for e in events if e["tool"] == "search_historical_policies" for m in json.loads(e["output_json"]).get("matches", [])}
    for atom in result["proposal"]["draft"].get("atoms", []):
        if not set(atom["evidence_ids"]).issubset(read_ids): raise ValueError("proposal cites unread evidence IDs: "+json.dumps(sorted(set(atom["evidence_ids"])-read_ids)))
        if atom.get("history_id") and (atom["history_id"], atom.get("history_hash")) not in retrieved: raise ValueError("reuse references history not retrieved by this job")
    if not any(e["tool"] == "validate_policy_draft" and json.loads(e["output_json"]).get("proposal_hash") == result["proposal_hash"] and (json.loads(e["output_json"]).get("valid") or json.loads(e["output_json"]).get("state")=="needs_clarification") for e in events):
        raise ValueError("submit the exact validated draft")
    if result['state'] not in ('validated','needs_clarification'): raise ValueError("compile failure blocks submission")
    ident = uuid.uuid4().hex
    with db.connect() as con:
        if con.execute("SELECT 1 FROM bootstrap_proposals WHERE job_id=?", (job_id,)).fetchone(): raise ValueError("job already submitted one proposal")
        con.execute("INSERT INTO bootstrap_proposals VALUES(?,?,?,?,?,?,?,?,?)", (ident, task_id, job_id, result["proposal"]["context_hash"], result["proposal_hash"], json.dumps(result["proposal"]), json.dumps({k:v for k,v in result.items() if k != "proposal"}), result['state'], db.now()))
    return {"id": ident, "proposal_hash": result["proposal_hash"], "state": result['state']}

#!/usr/bin/env python3
"""Real Pi + DSH + kernel S0-S4 acceptance. Oracle stays outside generator/Agent context."""
import hashlib
import json
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from scope_acceptance import api, change, review, STATE, URL
_task=None

def wait_for(predicate, seconds=180):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        value=predicate()
        if value:return value
        time.sleep(.25)
    raise RuntimeError("Real execution observation budget exceeded")

def plugin(task, token):
    request=urllib.request.Request(URL+"/api/plugin/tasks/"+task+"/scope-manager/gate",headers={"Authorization":"Bearer "+token})
    try:
        with urllib.request.urlopen(request) as response:return response.status
    except urllib.error.HTTPError as error:return error.code

def credential(pid):
    fields=(Path("/proc")/str(pid)/"environ").read_bytes().split(b"\0")
    return next(f.split(b"=",1)[1].decode() for f in fields if f.startswith(b"AGENTSCOPE_TASK_TOKEN="))

def run():
    global _task
    task=api("/api/scope-demo/tasks",{})["task_id"]
    _task=task
    base="/api/tasks/"+task+"/scope-manager"
    workspace=Path(api(base)["task"]["workspace"])
    print(json.dumps({"stage":"created","task":task}),flush=True)
    records={}
    records["S0"]=api(base+"/cold",{})
    assert records["S0"]["current"]["verification"]["root_owned_events"]
    records["S1"]=review(task,change(task,"task_grant","授权修改 backend/frontend，保护 tests/config，output 需要另行审批。"))
    initial=records["S1"]["current"]["binding"]
    execution=wait_for(lambda:api(base)["execution"].get("executor",{}).get("pid"),20)
    old_token=credential(execution)
    assert plugin(task,old_token)==200
    frontend_initial=hashlib.sha256(b'def summary(count):\n    return f"Words: {count}"\n').hexdigest()
    wait_for(lambda:hashlib.sha256((workspace/"frontend/report.py").read_bytes()).hexdigest()!=frontend_initial)
    before=api(base)
    records["S1_native_frontend_complete"]={"executor":before["execution"]["executor"],
        "frontend_hash":hashlib.sha256((workspace/"frontend/report.py").read_bytes()).hexdigest()}
    print(json.dumps({"stage":"S1_DSH_frontend_completed","task":task}),flush=True)
    records["S2"]=review(task,change(task,"restrict","暂时只修改 backend，停止修改 frontend；保护 tests/config。"))
    assert records["S2"]["current"]["binding"]["domain_id"]==initial["domain_id"]
    held=[c for c in records["S2"]["current"]["verification"]["probe"]["checks"] if c["name"]=="frontend:existing-fd"]
    assert held and held[0]["passed"] and not held[0]["allowed"]
    # Await DSH's own output request, rather than synthesizing it as a user request.
    def dsh_request():
        current=api(base)
        return next((d for d in current["deltas"] if d["kind"]=="expand" and
            any(e["source"]=="agent_request" and e["source_key"]==d["id"] and e["payload"]["actor"]=="DSH" for e in current["events"])),None)
    native=wait_for(dsh_request)
    native_source_id=native["id"]
    def ready():
        scope=api(base)
        d=next(d for d in scope["deltas"] if d["id"]==native["id"])
        job=next(j for j in scope["jobs"] if j["delta_id"]==native["id"])
        if job["status"] in ("failed","interrupted"):
            if str(job["error"]).startswith("stale:"):return {**d,"stale_analysis":True}
            raise RuntimeError(job["error"])
        return d if job["status"]=="completed" else None
    native=wait_for(ready)
    if native.get("stale_analysis") or native["base_snapshot_id"]!=records["S2"]["current"]["id"] or native["message_revision"]!=records["S2"]["session"]["message_revision"]:
        # A fast DSH may request output before the user's S2 message arrives.
        # Keep that real request as evidence; the simulated reviewer explicitly
        # reassesses it with the new context instead of approving a stale candidate.
        records["S3_stale_request"]={"native_request_id":native_source_id,"changes_permissions":False}
        native=change(task,"expand","依据 DSH 的公开申请，在当前已确认 Scope 上重新分析："+native["input"]["text"])
    assert not api(base)["current"]["payload"]["allow_output"]
    assert not (workspace.parent/"output/report.md").exists()
    rejected=review(task,native,"reject")
    assert rejected["current"]["id"]==records["S2"]["current"]["id"]
    records["S3_rejected"]=rejected
    # Explicit approval of a new output request after rejection.
    records["S3"]=review(task,change(task,"expand","允许 output 写入报告，保留 backend-only 和 tests/config 限制。"))
    assert records["S3"]["current"]["binding"]["domain_id"]!=initial["domain_id"]
    assert records["S3"]["current"]["payload"]["allowed_write_dirs"]==["backend"]
    assert plugin(task,old_token)==401
    wait_for(lambda:(workspace.parent/"output/report.md").is_file())
    wait_for(lambda:api(base)["execution"].get("executor",{}).get("state")=="absent")
    result=subprocess.run(["/usr/bin/python3","-B","-m","unittest","discover","-s","tests","-v"],cwd=workspace,capture_output=True,text=True)
    assert result.returncode==0
    git_commit=subprocess.check_output(["git","-c","safe.directory="+str(workspace),"rev-parse","HEAD"],cwd=workspace,text=True).strip()
    assert git_commit==api(base)["task"]["commit"]
    records["functional"]={"passed":True,"tests":3,"unittest":result.stderr,"git_commit":git_commit,
        "report_hash":hashlib.sha256((workspace.parent/"output/report.md").read_bytes()).hexdigest(),
        "frontend_changed":True,"old_token_rejected":True}
    observed=api(base)
    records["public_execution_events"]=[e for e in observed["events"] if e["source"] in ("tool_result","boundary_pause","boundary_context_delivery","agent_report","checkpoint")]
    assert any(e["source"]=="boundary_pause" for e in records["public_execution_events"]), "No real DSH tool-boundary pause"
    final_binding=observed["current"]["binding"]
    records["S4"]=api(base+"/close",{})
    assert not records["S4"]["effective"]
    for key in ("runner_pid","watch_pid"):
        proc=Path("/proc")/str(final_binding[key])
        assert not proc.exists() or "\nState:\tZ" in (proc/"status").read_text()
    next_task=api("/api/scope-demo/tasks",{})["task_id"]
    next_scope=api("/api/tasks/"+next_task+"/scope-manager")
    assert next_scope["current"] is None and not next_scope["default_scope"]["allow_output"]
    records["new_task"]={"task_id":next_task,"inherits_grants":False}
    records["passed"]=True
    dest=STATE/"report"/(task+"-full.json")
    dest.write_text(json.dumps(records,ensure_ascii=False,indent=2))
    print(json.dumps({"task":task,"passed":True,"stages":["S0","S1","S2","S3","S4"],"functional_tests":3,"evidence":str(dest)}),flush=True)

if __name__=="__main__":
    try: run()
    except Exception as error:
        if _task:
            scope=api("/api/tasks/"+_task+"/scope-manager")
            failure={"error":str(error),"scope":scope,"cleanup":api("/api/tasks/"+_task+"/scope-manager/close",{})}
            (STATE/"report"/(_task+"-failed.json")).write_text(json.dumps(failure,ensure_ascii=False,indent=2))
        raise

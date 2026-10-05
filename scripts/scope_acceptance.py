#!/usr/bin/env python3
"""Live isolated Demo driver. Never exports credentials, raw model output or hidden reasoning."""
import argparse
import json
import time
import urllib.request
from pathlib import Path
from scope_service import environment, STATE, URL

ENV = environment()
def api(path, body=None):
    request = urllib.request.Request(URL + path, data=None if body is None else json.dumps(body, ensure_ascii=False).encode(),
        headers={"Authorization": "Bearer " + ENV["AGENTSCOPE_ADMIN_TOKEN"], "Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=100) as response: return json.load(response)

def change(task, kind, text):
    current = api("/api/tasks/" + task + "/scope-manager")
    result = api("/api/tasks/" + task + "/scope-manager/changes", {"kind": kind, "text": text,
        "expected_snapshot": current["session"]["active_snapshot_id"], "request_key": kind + "-" + str(time.time_ns())})
    deadline = time.monotonic() + 200
    while time.monotonic() < deadline:
        scope = api("/api/tasks/" + task + "/scope-manager")
        delta = next(d for d in scope["deltas"] if d["id"] == result["id"])
        job = next(j for j in scope["jobs"] if j["delta_id"] == delta["id"])
        if job["status"] == "completed": return delta
        if job["status"] in ("failed", "interrupted"): raise RuntimeError(job["error"])
        time.sleep(1)
    raise RuntimeError("Pi candidate timed out")

def review(task, delta, decision="approve"):
    return api("/api/tasks/" + task + "/scope-manager/changes/" + delta["id"] + "/review",
               {"decision": decision, "expected_proposal_hash": delta["proposal_hash"], "reviewed_by": "授权 Demo 验收"})

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["cold", "grant", "restrict", "expand", "reject-expand", "status", "close"])
    parser.add_argument("--task")
    args = parser.parse_args()
    task = args.task
    if args.action == "cold":
        task = api("/api/scope-demo/tasks", {})["task_id"]
        result = api("/api/tasks/" + task + "/scope-manager/cold", {})
    elif args.action == "status": result = api("/api/tasks/" + task + "/scope-manager")
    elif args.action == "close": result = api("/api/tasks/" + task + "/scope-manager/close", {})
    else:
        kind, text = {"grant": ("task_grant", "授权修改 backend 和 frontend，保护 tests/config，报告 output 需要单独审批。"),
                      "restrict": ("restrict", "暂时只修改 backend，停止修改 frontend，继续保护 tests/config。"),
                      "expand": ("expand", "本次仅授权 output 写入报告，保留此前已生效的所有仓库限制。"),
                      "reject-expand": ("expand", "申请 output 写入报告，保持此前仓库限制。")}[args.action]
        delta = change(task, kind, text)
        result = review(task, delta, "reject" if args.action == "reject-expand" else "approve")
    dest = STATE / "report" / (task + "-" + args.action + ".json")
    dest.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    current = result.get("current")
    print(json.dumps({"task": task, "action": args.action, "effective": result["effective"],
        "revision": current["revision"] if current else None, "gate": result["session"]["gate"],
        "domain": current["binding"]["domain_id"] if current else None,
        "probe_passed": current["verification"]["passed"] if current else None, "evidence": str(dest)}, ensure_ascii=False))

#!/usr/bin/env python3
"""Root-local acceptance control client. Never prints authorization data."""
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

STATE = Path("/var/lib/agentscope-rq5-v1")
def request(path, body=None):
    headers = {"Authorization": "Bearer " + (STATE / "admin-token").read_text(), "Content-Type": "application/json"}
    query = urllib.request.Request("http://127.0.0.1:18001" + path, None if body is None else json.dumps(body).encode(), headers)
    try:
        with urllib.request.urlopen(query, timeout=65) as response: return json.load(response)
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"HTTP {error.code}: " + error.read().decode()[:2000]) from None

if __name__ == "__main__":
    action = sys.argv[1]
    if action == "create":
        data = request(f"/api/rq5/scenarios/{sys.argv[2]}/tasks", {})
        print(json.dumps(data))
    elif action == "generate": print(json.dumps(request(f"/api/tasks/{sys.argv[2]}/bootstrap", {})))
    elif action == "state":
        data = request(f"/api/tasks/{sys.argv[2]}/bootstrap")
        print(json.dumps({"jobs": data["jobs"], "proposals": [{"id": p["id"], "hash": p["content_hash"], "proposal": p["proposal"]} for p in data["proposals"]],
                          "events": [{"tool": e["tool"], "diagnostic": e["output"].get("diagnostic"), "valid": e["output"].get("valid")} for e in data["tool_events"]]}, ensure_ascii=False))

"""Trusted local launcher. Emits only a short-lived ticket, never an admin credential."""
import json
from scope_acceptance import api
from scope_service import URL
ticket=api("/api/auth/local-browser-ticket", {})["ticket"]
tasks=api("/api/tasks")
task=next((t["id"] for t in tasks if t["repo"]=="AgentScope/custom-scope-demo" and t["status"]=="completed"),"")
url=URL+"/?view=scope-demo"+("&task="+task if task else "")+"#local-launch="+ticket
print(json.dumps({"url":url,"expires_in":300}))

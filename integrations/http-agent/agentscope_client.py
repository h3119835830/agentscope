"""Dependency-free execution-Agent adapter. Credentials stay in caller memory/env."""
import ipaddress
import json
import os
import uuid
from urllib.error import HTTPError
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        # A task credential must never be forwarded to a redirect destination.
        return None


class AgentScopeError(RuntimeError):
    def __init__(self, status, detail):
        self.status = status
        super().__init__(detail)


class AgentScopeClient:
    def __init__(self, base_url, task_id, token, timeout=8):
        parsed = urlsplit(base_url)
        try:
            local = parsed.hostname == "localhost" or ipaddress.ip_address(parsed.hostname).is_loopback
        except ValueError:
            local = False
        if parsed.scheme not in ("http", "https") or (parsed.scheme != "https" and not local):
            raise ValueError("Use HTTPS for remote AgentScope connections")
        if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ("", "/"):
            raise ValueError("Base URL must be an origin without credentials")
        if not task_id or not token:
            raise ValueError("Task ID and task-scoped token are required")
        self.base_url = base_url.rstrip("/")
        self.task_id = task_id
        self.token = token
        self.timeout = timeout
        self.current = None
        self._opener = build_opener(NoRedirect())

    @classmethod
    def from_environment(cls):
        return cls(os.environ["AGENTSCOPE_URL"], os.environ["AGENTSCOPE_TASK_ID"], os.environ["AGENTSCOPE_TASK_TOKEN"])

    def _call(self, path, body=None):
        request = Request(f"{self.base_url}/api/agent/tasks/{quote(self.task_id, safe='')}{path}",
                          data=None if body is None else json.dumps(body).encode(),
                          headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
                          method="GET" if body is None else "POST")
        try:
            with self._opener.open(request, timeout=self.timeout) as response:
                return json.load(response)
        except HTTPError as error:
            try:
                detail = json.load(error).get("detail", "AgentScope request failed")
            except (ValueError, AttributeError):
                detail = "AgentScope request failed"
            raise AgentScopeError(error.code, str(detail)) from None

    def context(self):
        self.current = self._call("/context")
        return self.current

    def messages(self, after=0, limit=20):
        # Keep the cursor until handlers durably finish; replay and receipts survive reconnects.
        return self._call(f"/messages?after={int(after)}&limit={int(limit)}")

    def acknowledge(self, message_id, status="received"):
        return self._call(f"/messages/{quote(message_id, safe='')}/ack", {"status": status})

    def _bound(self, fields, request_key):
        current = self.current or self.context()
        return {**fields, "request_key": request_key or uuid.uuid4().hex,
                "expected_snapshot_hash": current["snapshot_hash"]}

    def report(self, kind, summary, operation="", target="", request_key=None):
        return self._call("/feedback", self._bound({"kind": kind, "summary": summary, "operation": operation, "target": target}, request_key))

    def request_scope(self, kind, justification, path=None, request_key=None):
        return self._call("/scope-requests", self._bound({"kind": kind, "path": path, "justification": justification}, request_key))

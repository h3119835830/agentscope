import json
import os
import threading
from pathlib import Path
from .. import db
from . import manager

class Worker:
    def __init__(self):
        self.stop_event = threading.Event()
        self.thread = None
        self.collector = None

    def start(self):
        if os.getenv("AGENTSCOPE_SCOPE_WORKER", "0") != "1": return
        with db.connect() as con:
            con.execute("UPDATE scope_jobs SET status='interrupted',token_hash=NULL,error='服务重启中断，需重新分析' WHERE status='running'")
            con.execute("UPDATE scope_sessions SET gate='failed',apply_id=NULL WHERE apply_id IS NOT NULL")
        self.stop_event.clear()
        self.thread = threading.Thread(target=self.loop, name="scope-worker", daemon=True)
        self.thread.start()
        self.collector = threading.Thread(target=self.collect_loop, name="scope-events", daemon=True)
        self.collector.start()

    def stop(self):
        self.stop_event.set()
        if self.thread: self.thread.join(timeout=2)
        if self.collector: self.collector.join(timeout=2)

    def collect_loop(self):
        while not self.stop_event.is_set():
            try: self.collect()
            except Exception:
                with db.connect() as con: db.audit(con, None, "scope_collect_error", "ScopeManager", {})
            self.stop_event.wait(.75)

    def collect(self):
        with db.connect() as con: tasks = [dict(r) for r in con.execute("SELECT t.* FROM tasks t JOIN scope_sessions s ON s.task_id=t.id WHERE s.phase!='ended'")]
        for task in tasks:
            path = Path(task["workspace"]) / ".actplane/events.jsonl"
            try:
                metadata = path.lstat()
                if path.is_symlink() or metadata.st_uid != 0 or metadata.st_mode & 0o022: continue
                lines = path.read_text().splitlines()
            except OSError: continue
            with db.connect() as con:
                verification = [json.loads(r["verification_json"]) for r in con.execute(
                    "SELECT verification_json FROM scope_snapshots WHERE task_id=?", (task["id"],))]
            probes = {(v.get("domain_id"), v.get("probe", {}).get("probe_pid")) for v in verification}
            for line in lines:
                try: raw = json.loads(line)
                except ValueError: continue
                with db.connect() as con:
                    session = con.execute("SELECT active_snapshot_id,process_epoch FROM scope_sessions WHERE task_id=?", (task["id"],)).fetchone()
                    manager.event(con, task["id"], "kernel", manager.digest(raw), {"event": raw, "observed_snapshot": session["active_snapshot_id"],
                                  "process_epoch": session["process_epoch"], "assessment": "existing_boundary_no_automatic_grant"})
                    pending = con.execute("SELECT 1 FROM scope_jobs WHERE task_id=? AND status IN ('queued','running')", (task["id"],)).fetchone()
                    control = con.execute("SELECT * FROM scope_sessions WHERE task_id=?", (task["id"],)).fetchone()
                target = str(raw.get("target", ""))
                # Disposable verification files are never interpreted as a model's need.
                if (raw.get("domain_id"), raw.get("pid")) in probes or (raw.get("domain_id"), raw.get("ppid")) in probes: continue
                if "/scope-" in target or "/.actplane/" in target or not raw.get("blocked"): continue
                if pending or control["phase"] != "running" or control["gate"] != "open" or control["apply_id"]: continue
                key = manager.digest({"domain": raw.get("domain_id"), "target": target, "op": raw.get("op")})
                from .models import ChangeRequest
                manager.assess(task["id"], ChangeRequest(kind="guidance", text="运行时拒绝事件：" + str(raw.get("op")) + " " + target +
                    "。核验现有边界是否已覆盖；此事件本身不构成扩权授权。", request_key="kernel-" + key,
                    expected_snapshot=control["active_snapshot_id"]), actor="内核事件")

    def run_one(self):
        with db.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            job = con.execute("SELECT * FROM scope_jobs WHERE status='queued' ORDER BY created_at LIMIT 1").fetchone()
            if not job: return False
            job = dict(job)
            if not con.execute("UPDATE scope_jobs SET status='running' WHERE id=? AND status='queued'", (job["id"],)).rowcount: return True
            delta = dict(con.execute("SELECT * FROM scope_deltas WHERE id=?", (job["delta_id"],)).fetchone())
            try: context = manager.context_for(con, delta)
            except ValueError as error:
                con.execute("UPDATE scope_jobs SET status='failed',error=? WHERE id=?", (str(error), job["id"]))
                return True
            con.execute("UPDATE scope_jobs SET result_json=? WHERE id=?", (json.dumps({"context": context}), job["id"]))
        try:
            from .pi import generate
            runtime = generate(job)
            with db.connect() as con:
                # A concurrently accepted user message or installed Scope makes
                # this immutable analysis stale, even if Pi did not submit.
                manager.context_for(con, delta)
                row = con.execute("SELECT proposal_hash FROM scope_deltas WHERE id=?", (job["delta_id"],)).fetchone()
                if not row["proposal_hash"]: raise ValueError("Pi 结束但未提交候选")
                con.execute("UPDATE scope_jobs SET status='completed',token_hash=NULL,result_json=? WHERE id=? AND status='running'",
                            (json.dumps({"context": context, "runtime": runtime}), job["id"]))
        except Exception as error:
            with db.connect() as con:
                con.execute("UPDATE scope_jobs SET status='failed',token_hash=NULL,error=? WHERE id=? AND status='running'", (str(error)[:1000], job["id"]))
                manager.event(con, job["task_id"], "analysis_failure", job["id"], {"error": str(error)[:1000]})
        return True

    def loop(self):
        while not self.stop_event.is_set():
            try:
                if self.run_one(): continue
            except Exception as error:
                with db.connect() as con: db.audit(con, None, "scope_worker_error", "ScopeManager", {"type": type(error).__name__})
            self.stop_event.wait(.5)

worker = Worker()

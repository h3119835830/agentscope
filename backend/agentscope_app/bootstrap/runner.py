"""One-shot Pi with exactly seven API tools in a minimal read-only runtime mount."""
import json
import os
import signal
import subprocess
import tempfile
import time
from pathlib import Path
from .. import db
from ..config import PUBLIC_BASE_URL, STATE_DIR
from .tools import TOOLS, issue, revoke
from .scene import digest

INTEGRATION = Path(__file__).resolve().parents[3] / "integrations/pi-policy-tools"

def run(task_id,job_id):
    try:return _run(task_id,job_id)
    finally:
        revoke(job_id)
        with db.connect() as con:
            con.execute("UPDATE tasks SET status='prepared',updated_at=? WHERE id=? AND status='bootstrapping' AND NOT EXISTS (SELECT 1 FROM history_jobs WHERE kind='task_bootstrap' AND json_extract(input_json,'$.task_id')=? AND id<>? AND status IN ('queued','running'))", (db.now(), task_id,task_id,job_id))

def _run(task_id, job_id):
    root = STATE_DIR / "pi-jobs"
    root.mkdir(mode=0o700, exist_ok=True)
    token = issue(task_id, job_id)
    runtime={"package":"@earendil-works/pi-coding-agent","version":"1.0.1","model":"deepseek-flash","thinking":"off",
             "extension_hash":digest((INTEGRATION/"extension.ts").read_text()),"skill_hash":digest((INTEGRATION/"bootstrap-system.md").read_text()),
             "workflow_version":"task-scope-bootstrap/1.0.1",
             "lock_hash":digest((INTEGRATION/"package-lock.json").read_text()),"allowed_tools":TOOLS,"sandbox":"bwrap; no project, oracle, database or task filesystem mount"}
    with db.connect() as con:
        row=con.execute("SELECT input_json FROM history_jobs WHERE id=?",(job_id,)).fetchone()
        con.execute("UPDATE history_jobs SET input_json=? WHERE id=?",(json.dumps({**json.loads(row[0]),"runtime":runtime}),job_id))
    try:
        package=json.loads((INTEGRATION/"node_modules/@earendil-works/pi-coding-agent/package.json").read_text())
        if package["version"]!="1.0.1":raise ValueError("Pi package version differs from fixed runtime")
        key = os.getenv("AGENTSCOPE_HISTORY_LLM_KEY") or os.getenv("DEEPSEEK_API_KEY")
        if not key: raise ValueError("DeepSeek generation credential is not configured")
        with tempfile.TemporaryDirectory(prefix=job_id + "-", dir=root) as directory:
            home = Path(directory)
            agent = home / "agent"
            agent.mkdir(mode=0o700)
            model = {"providers": {"agentscope-deepseek": {"baseUrl": os.getenv("AGENTSCOPE_HISTORY_LLM_URL", "https://api.deepseek.com"),
                      "api": "openai-completions", "apiKey": "${DEEPSEEK_API_KEY}",
                      "models": [{"id": "deepseek-flash", "reasoning": False, "contextWindow": 1000000, "maxTokens": 12000,
                                  "compat": {"supportsStore": False, "supportsDeveloperRole": False, "supportsReasoningEffort": False}}]}}}
            (agent / "models.json").write_text(json.dumps(model))
            (agent / "settings.json").write_text(json.dumps({"packages": [], "defaultThinkingLevel": "off", "checkForUpdates": False}))
            environment = {"PATH": "/usr/bin:/bin", "HOME": "/home/pi", "PI_CODING_AGENT_DIR": "/home/pi/agent", "LANG": "C.UTF-8",
                           "DEEPSEEK_API_KEY": key, "AGENTSCOPE_GENERATOR_TOKEN": token, "AGENTSCOPE_GENERATOR_TASK": task_id,
                           "AGENTSCOPE_GENERATOR_JOB": job_id, "AGENTSCOPE_GENERATOR_URL": PUBLIC_BASE_URL}
            cli = ["/runtime/node", "/pi/node_modules/@earendil-works/pi-coding-agent/dist/cli.js", "--print", "--no-session",
                   "--provider", "agentscope-deepseek", "--model", "deepseek-flash", "--thinking", "off", "--no-builtin-tools",
                   "--tools", ",".join(TOOLS), "--no-extensions", "--extension", "/pi/extension.ts", "--no-skills",
                   "--no-context-files", "--no-prompt-templates", "--no-themes", "--no-approve", "--offline", "--system-prompt", "/pi/bootstrap-system.md",
                   "Generate the startup policy for the task bound to your tools. Complete the evidence/retrieval/validation/submission workflow. Do not execute the task."]
            command = ["/usr/bin/bwrap", "--die-with-parent", "--unshare-pid", "--unshare-ipc", "--unshare-uts",
                       "--ro-bind", "/usr", "/usr", "--ro-bind", "/lib", "/lib", "--ro-bind", "/lib64", "/lib64",
                       "--ro-bind", "/etc/ssl", "/etc/ssl", "--ro-bind", "/etc/resolv.conf", "/etc/resolv.conf",
                       "--ro-bind", "/etc/hosts", "/etc/hosts", "--ro-bind", "/opt/agentscope/bin/node", "/runtime/node",
                       "--ro-bind", str(INTEGRATION), "/pi", "--bind", directory, "/home/pi",
                       "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp", "--chdir", "/home/pi", "--", *cli]
            process = subprocess.Popen(command, env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
            deadline=time.monotonic()+180
            while True:
                try: stdout,stderr=process.communicate(timeout=min(1,max(.01,deadline-time.monotonic())));break
                except subprocess.TimeoutExpired:
                    with db.connect() as con:status=con.execute("SELECT status FROM history_jobs WHERE id=?",(job_id,)).fetchone()[0]
                    if status!="running" or time.monotonic()>=deadline:
                        os.killpg(process.pid,signal.SIGKILL);process.communicate()
                        raise ValueError("Pi interrupted or exceeded 180 seconds; process group killed")
            if process.returncode: raise ValueError("Pi process failed (exit %s); check configuration or model availability" % process.returncode)
            # Neither reasoning streams nor ambient credential-bearing process output are persisted.
            with db.connect() as con:
                proposal = con.execute("SELECT id,content_hash,state FROM bootstrap_proposals WHERE job_id=?", (job_id,)).fetchone()
                calls = con.execute("SELECT calls FROM bootstrap_credentials WHERE job_id=?", (job_id,)).fetchone()[0]
            if not proposal: raise ValueError("Pi exited without a validated submitted proposal")
            if digest((INTEGRATION/"extension.ts").read_text())!=runtime["extension_hash"] or digest((INTEGRATION/"bootstrap-system.md").read_text())!=runtime["skill_hash"]:raise ValueError("Pi integration changed during generation")
            return {"proposal_id": proposal["id"], "proposal_hash": proposal["content_hash"], "proposal_state":proposal['state'], "tool_calls": calls,"runtime":runtime}
    finally:
        revoke(job_id)
        with db.connect() as con:
            con.execute("UPDATE tasks SET status='prepared',updated_at=? WHERE id=? AND status='bootstrapping' AND NOT EXISTS (SELECT 1 FROM history_jobs WHERE kind='task_bootstrap' AND json_extract(input_json,'$.task_id')=? AND id<>? AND status IN ('queued','running'))", (db.now(), task_id,task_id,job_id))

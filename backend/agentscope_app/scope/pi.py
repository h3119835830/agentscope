"""Restricted Pi runtime: immutable API evidence only, short-lived candidate credentials."""
import json
import os
import secrets
import signal
import subprocess
import tempfile
import time
from pathlib import Path
from .. import db
from ..config import PUBLIC_BASE_URL, STATE_DIR
from .manager import digest

INTEGRATION = Path(__file__).resolve().parents[3] / "integrations/pi-policy-tools"
TOOLS = ["get_runtime_context", "search_reviewed_history", "submit_scope_proposal"]

def generate(job):
    token = secrets.token_urlsafe(36)
    with db.connect() as con:
        con.execute("UPDATE scope_jobs SET token_hash=?,expires_at=? WHERE id=? AND status='running'", (digest(token), time.time() + 180, job["id"]))
    key = os.getenv("AGENTSCOPE_HISTORY_LLM_KEY") or os.getenv("DEEPSEEK_API_KEY")
    if not key: raise ValueError("Pi 模型服务未配置")
    root = STATE_DIR / "scope-pi"
    root.mkdir(mode=0o700, exist_ok=True)
    runtime = {"package": "@earendil-works/pi-coding-agent", "version": "1.0.1", "thinking": "off",
               "tools": TOOLS, "extension_hash": digest((INTEGRATION / "runtime-extension.ts").read_text()),
               "system_hash": digest((INTEGRATION / "runtime-system.md").read_text()),
               "lock_hash": digest((INTEGRATION / "package-lock.json").read_text()),
               "sandbox": "bwrap; no task/oracle/database mount"}
    with tempfile.TemporaryDirectory(dir=root, prefix=job["id"] + "-") as directory:
        home = Path(directory)
        (home / "agent").mkdir()
        (home / "agent/models.json").write_text(json.dumps({"providers": {"agentscope-deepseek": {
            "baseUrl": os.getenv("AGENTSCOPE_HISTORY_LLM_URL", "https://api.deepseek.com"), "api": "openai-completions",
            "apiKey": "$" + "{DEEPSEEK_API_KEY}", "models": [{"id": "deepseek-flash", "reasoning": False, "contextWindow": 1000000,
            "maxTokens": 4000, "compat": {"supportsStore": False, "supportsDeveloperRole": False, "supportsReasoningEffort": False}}]}}}))
        (home / "agent/settings.json").write_text(json.dumps({"packages": [], "checkForUpdates": False}))
        env = {"PATH": "/usr/bin:/bin", "HOME": "/home/pi", "PI_CODING_AGENT_DIR": "/home/pi/agent",
               "LANG": "C.UTF-8", "DEEPSEEK_API_KEY": key, "AGENTSCOPE_SCOPE_URL": PUBLIC_BASE_URL,
               "AGENTSCOPE_SCOPE_TASK": job["task_id"], "AGENTSCOPE_SCOPE_JOB": job["id"], "AGENTSCOPE_SCOPE_TOKEN": token}
        command = ["/usr/bin/bwrap", "--die-with-parent", "--unshare-pid", "--unshare-ipc", "--unshare-uts",
                   "--ro-bind", "/usr", "/usr", "--ro-bind", "/lib", "/lib", "--ro-bind", "/lib64", "/lib64",
                   "--ro-bind", "/etc/ssl", "/etc/ssl", "--ro-bind", "/etc/resolv.conf", "/etc/resolv.conf",
                   "--ro-bind", "/etc/hosts", "/etc/hosts", "--ro-bind", "/opt/agentscope/bin/node", "/runtime/node",
                   "--ro-bind", str(INTEGRATION / "runtime-extension.ts"), "/pi/runtime-extension.ts",
                   "--ro-bind", str(INTEGRATION / "runtime-system.md"), "/pi/runtime-system.md",
                   "--ro-bind", str((INTEGRATION / "node_modules").resolve()), "/pi/node_modules",
                   "--bind", directory, "/home/pi", "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
                   "--chdir", "/home/pi", "--", "/runtime/node", "/pi/node_modules/@earendil-works/pi-coding-agent/dist/cli.js",
                   "--print", "--no-session", "--provider", "agentscope-deepseek", "--model", "deepseek-flash", "--thinking", "off",
                   "--no-builtin-tools", "--tools", ",".join(TOOLS), "--no-extensions", "--extension", "/pi/runtime-extension.ts",
                   "--no-skills", "--no-context-files", "--no-prompt-templates", "--no-themes", "--no-approve", "--offline",
                   "--system-prompt", "/pi/runtime-system.md", "Assess the bound Scope change using its immutable context and submit one supported candidate."]
        process = subprocess.Popen(command, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
        deadline = time.monotonic() + 180
        while True:
            try:
                stdout, stderr = process.communicate(timeout=1)
                break
            except subprocess.TimeoutExpired:
                with db.connect() as con: state = con.execute("SELECT status FROM scope_jobs WHERE id=?", (job["id"],)).fetchone()[0]
                if state != "running" or time.monotonic() >= deadline:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.communicate()
                    raise ValueError("Pi 分析中断或超过预算")
        if process.returncode: raise ValueError("Pi 进程失败 exit=" + str(process.returncode))
    if runtime["extension_hash"] != digest((INTEGRATION / "runtime-extension.ts").read_text()) or runtime["system_hash"] != digest((INTEGRATION / "runtime-system.md").read_text()) or runtime["lock_hash"] != digest((INTEGRATION / "package-lock.json").read_text()):
        raise ValueError("生成期间 Pi 固定输入发生漂移")
    return runtime

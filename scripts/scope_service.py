#!/usr/bin/env python3
"""Explicitly isolated file-scope Demo instance; preserves all existing instance data."""
import grp
import json
import os
import pwd
import shutil
import signal
import subprocess
import time
from pathlib import Path
from rq5_service import environment as base_environment

ROOT = Path(__file__).resolve().parents[1]
STATE = Path("/var/lib/agentscope-scope-demo")
TASKS = Path("/s")
URL = "http://127.0.0.1:18003"


def environment():
    env = base_environment()
    env.update({"AGENTSCOPE_STATE_DIR": str(STATE), "AGENTSCOPE_DB": str(STATE / "demo.sqlite3"),
                "AGENTSCOPE_TASK_ROOT": str(TASKS), "AGENTSCOPE_POLICY_DIR": str(STATE / "policies"),
                "AGENTSCOPE_LOG_DIR": str(STATE / "logs"), "AGENTSCOPE_RUNTIME_DIR": "/run/agentscope-scope-demo",
                "AGENTSCOPE_BROKER_SOCKET": "/run/agentscope-scope-demo/broker.sock", "AGENTSCOPE_PUBLIC_URL": URL,
                "AGENTSCOPE_SERVICE_HOME": str(STATE), "AGENTSCOPE_UI_DIST": str(STATE / "ui"),
                "AGENTSCOPE_DSH_HOME": str(STATE / "dsh-home"), "DSH_HOME": str(STATE / "dsh-home"),
                "ACTPLANE_BPF_PIN_ROOT": "/sys/fs/bpf/agentscope-managed-v3",
                "AGENTSCOPE_SCOPE_WORKER": "1", "AGENTSCOPE_BOOTSTRAP_TEST_LIBRARY": "1",
                "AGENTSCOPE_DEV_NO_AUTH": "1", "AGENTSCOPE_RQ1_AUTO_IMPORT": "0",
                "PYTHONPATH": str(ROOT / "backend"), "AGENTSCOPE_RUNNER": str(ROOT / "backend/broker/task_runner.py")})
    env.pop("AGENTSCOPE_ADMIN_TOKEN", None)
    if (STATE / "bin/actplane").exists(): env["ACTPLANE_BIN"] = str(STATE / "bin/actplane")
    env["DSH_BIN"] = str(STATE / "dsh-home/profiles/headless/node_modules/@deepseek-ai/dsh/lib/bin.js")
    return env


def start(api_only=False):
    if os.getuid() != 0: raise SystemExit("isolated broker setup requires root")
    user, group = pwd.getpwnam("agentscope-api"), grp.getgrnam("agentscope-task")
    STATE.mkdir(exist_ok=True)
    os.chown(STATE, user.pw_uid, group.gr_gid)
    STATE.chmod(0o750)
    if TASKS.exists() and not (STATE / "ownership.json").exists(): raise SystemExit("Refusing unowned /s")
    TASKS.mkdir(exist_ok=True)
    os.chown(TASKS, user.pw_uid, group.gr_gid)
    TASKS.chmod(0o2770)
    (STATE / "ownership.json").write_text(json.dumps({"task_root": str(TASKS), "purpose": "synthetic scope demo"}))
    for name in ("policies", "logs", "report", "import/corpus"):
        p = STATE / name
        p.mkdir(parents=True, exist_ok=True)
        os.chown(p, user.pw_uid, group.gr_gid)
        p.chmod(0o750)
    if not (STATE / "ui").exists(): shutil.copytree(ROOT / "frontend/dist", STATE / "ui")
    home = STATE / "dsh-home"
    if not home.exists():
        source = Path("/var/lib/agentscope-history-v1/dsh-home")
        shutil.copytree(source, home, symlinks=True, ignore=shutil.ignore_patterns("sessions", "storages"))
        agent = pwd.getpwnam("agentscope-agent")
        for base, dirs, files in os.walk(home):
            os.chown(base, agent.pw_uid, group.gr_gid)
            os.chmod(base, 0o750)
            for name in files:
                p = Path(base) / name
                if not p.is_symlink(): os.chown(p, agent.pw_uid, group.gr_gid); os.chmod(p, 0o640)
    # Resolve the private profile package before copying; never edit the shared profile.
    plugin = home / "profiles/headless/node_modules/@agentscope/dsh-policy"
    if plugin.is_symlink():
        plugin.unlink()
        shutil.copytree(ROOT / "integrations/dsh-agentscope", plugin, symlinks=True)
    shutil.copy2(ROOT / "integrations/dsh-agentscope/lib/index.js", plugin / "lib/index.js")
    env = environment()
    pidfile = STATE / "service-pids.json"
    old = json.loads(pidfile.read_text()) if pidfile.exists() else {}
    if not api_only and old.get("broker") and Path("/proc", str(old["broker"])).exists():
        import sqlite3
        with sqlite3.connect(STATE / "demo.sqlite3") as database:
            bindings = database.execute("SELECT watch_pid FROM tasks WHERE watch_pid IS NOT NULL").fetchall()
        if any(Path("/proc", str(row[0])).exists() for row in bindings):
            raise RuntimeError("Close managed tasks before restarting the isolated broker")
    for role, pid in old.items():
        if api_only and role == "broker": continue
        path = Path("/proc") / str(pid)
        if path.exists():
            if str(STATE / "demo.sqlite3").encode() not in (path / "environ").read_bytes(): raise SystemExit("Service identity mismatch")
            os.kill(pid, signal.SIGTERM)
    if old: time.sleep(1)
    for port_check in range(30):
        if all(not Path("/proc", str(pid)).exists() for pid in old.values()): break
        time.sleep(.2)
    def demote():
        os.initgroups(user.pw_name, user.pw_gid)
        os.setgid(user.pw_gid)
        os.setuid(user.pw_uid)
    broker = None if api_only else subprocess.Popen(["/opt/agentscope/.venv/bin/python", str(ROOT / "backend/broker/main.py")],
        env=env, cwd=ROOT, stdout=open(STATE / "broker.log", "a"), stderr=subprocess.STDOUT, start_new_session=True)
    api = subprocess.Popen(["/opt/agentscope/.venv/bin/python", "-m", "uvicorn", "agentscope_app.main:app", "--host", "127.0.0.1", "--port", "18003"],
        env=env, cwd=ROOT, preexec_fn=demote, stdout=open(STATE / "api.log", "a"), stderr=subprocess.STDOUT, start_new_session=True)
    pids = {"broker": old["broker"] if api_only else broker.pid, "api": api.pid}
    pidfile.write_text(json.dumps(pids))
    import urllib.request
    for attempt in range(50):
        try:
            with urllib.request.urlopen(URL + "/api/health", timeout=1) as response:
                if response.status == 200: break
        except Exception: time.sleep(.2)
    else: raise RuntimeError("Isolated API did not become healthy")
    print(json.dumps({"url": URL, "database": str(STATE / "demo.sqlite3"), "pids": pids}))


if __name__ == "__main__":
    import sys
    start("--api-only" in sys.argv)

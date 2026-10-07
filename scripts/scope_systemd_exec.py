#!/usr/bin/env python3
"""Run only the prepared 18003 Scope Demo under separate systemd units."""
import fcntl
import json
import os
import pwd
import socket
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from scope_service import ROOT, STATE, PORT, URL, environment


def ready(role):
    if role == "broker-ready":
        user = pwd.getpwnam("agentscope-api")
        os.initgroups(user.pw_name, user.pw_gid)
        os.setgid(user.pw_gid)
        os.setuid(user.pw_uid)
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        try:
            if role == "broker-ready":
                with socket.socket(socket.AF_UNIX) as connection:
                    connection.settimeout(1)
                    connection.connect("/run/agentscope-scope-demo/broker.sock")
                    connection.sendall(b'{"action":"health"}\n')
                    payload = json.loads(connection.makefile("rb").readline(65536))
                    if payload.get("ok") is not True or not payload.get("result", {}).get("available"):
                        raise RuntimeError("Scope broker is not ready")
            else:
                with urllib.request.urlopen(URL + "/api/health", timeout=1) as response:
                    if response.status != 200:
                        raise RuntimeError("Scope API is not ready")
            return
        except (OSError, ValueError, RuntimeError):
            time.sleep(.2)
    raise SystemExit("Scope service readiness timed out")


def record_pid(role):
    with (STATE / "service-pids.lock").open("a") as lock:
        os.chmod(lock.name, 0o600)
        fcntl.flock(lock, fcntl.LOCK_EX)
        target = STATE / "service-pids.json"
        pids = json.loads(target.read_text()) if target.exists() else {}
        pids[role] = os.getpid()
        descriptor, name = tempfile.mkstemp(prefix=".service-pids-", dir=STATE)
        try:
            with os.fdopen(descriptor, "w") as output:
                json.dump(pids, output)
                output.flush()
                os.fsync(output.fileno())
            os.replace(name, target)
        finally:
            Path(name).unlink(missing_ok=True)


def main():
    if STATE != Path("/var/lib/agentscope-scope-demo") or PORT != 18003:
        raise SystemExit("This service supports only the 18003 Scope Demo profile")
    if len(sys.argv) != 2 or sys.argv[1] not in ("api", "broker", "api-ready", "broker-ready"):
        raise SystemExit("Expected api, broker, api-ready, or broker-ready")
    role = sys.argv[1]
    if role.endswith("-ready"):
        ready(role)
        return
    if os.getuid() != 0:
        raise SystemExit("Use the installed Scope Demo service units")
    if not (STATE / "demo.sqlite3").is_file() or not (STATE / "ui/index.html").is_file():
        raise SystemExit("Prepare the isolated Scope Demo before installing its services")
    env = environment()
    record_pid(role)
    python = "/opt/agentscope/.venv/bin/python"
    if role == "broker":
        command = [python, str(ROOT / "backend/broker/main.py")]
    else:
        user = pwd.getpwnam("agentscope-api")
        os.initgroups(user.pw_name, user.pw_gid)
        os.setgid(user.pw_gid)
        os.setuid(user.pw_uid)
        command = [python, "-m", "uvicorn", "agentscope_app.main:app", "--host", "127.0.0.1", "--port", "18003"]
    os.chdir(ROOT)
    os.execve(python, command, env)


if __name__ == "__main__":
    main()

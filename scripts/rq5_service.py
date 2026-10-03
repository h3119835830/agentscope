#!/usr/bin/env python3
"""Start a segregated local acceptance API/broker. No credentials are printed."""
import argparse
import grp
import json
import os
import pwd
import secrets
import shlex
import signal
import shutil
import subprocess
from pathlib import Path

ROOT = Path("/opt/agentscope")
STATE = Path("/var/lib/agentscope-rq5-v1")

def environment():
    env = os.environ.copy()
    for line in Path("/etc/agentscope/agentscope.env").read_text().splitlines():
        if not line.strip() or line.lstrip().startswith("#"): continue
        key, value = line.split("=", 1)
        parsed = shlex.split(value)
        env[key] = parsed[0] if len(parsed) == 1 else value
    env.update({"AGENTSCOPE_STATE_DIR": str(STATE), "AGENTSCOPE_DB": str(STATE / "acceptance.sqlite3"),
                "AGENTSCOPE_TASK_ROOT": "/r", "AGENTSCOPE_POLICY_DIR": str(STATE / "policies"),
                "AGENTSCOPE_LOG_DIR": str(STATE / "logs"), "AGENTSCOPE_RUNTIME_DIR": "/run/agentscope-rq5-v1",
                "AGENTSCOPE_BROKER_SOCKET": "/run/agentscope-rq5-v1/broker.sock", "AGENTSCOPE_PUBLIC_URL": "http://127.0.0.1:18001",
                "AGENTSCOPE_APP_USER": "agentscope-api", "AGENTSCOPE_SERVICE_HOME": str(STATE),
                "AGENTSCOPE_BOOTSTRAP_TEST_LIBRARY": "1", "AGENTSCOPE_RQ1_AUTO_IMPORT": "0", "AGENTSCOPE_HISTORY_WORKER": "1",
                "AGENTSCOPE_DSH_DISABLE_BYTECODE":"1",
                "AGENTSCOPE_UI_DIST": str(ROOT / "frontend/dist"), "PYTHONPATH": str(ROOT / "backend")})
    env["AGENTSCOPE_DSH_HOME"] = str(STATE / "dsh-home")
    if (STATE/'task-python/runtime-facts.json').exists():
        env['AGENTSCOPE_EXPERIMENT_PYTHON_RUNTIME']=str(STATE/'task-python')
        env['AGENTSCOPE_EXEC_PATH']=str(STATE/'task-python/bin')+':/opt/agentscope/bin:/opt/agentscope/dsh/node_modules/.bin:/usr/local/bin:/usr/bin:/bin'
    return env

def main():
    parser = argparse.ArgumentParser(); parser.add_argument("action", choices=["start", "status", "restart-api", "restart"])
    parser.add_argument('--use-installed-admin',action='store_true',help='Use the existing locally configured administrator identity; keep the value private')
    args = parser.parse_args()
    if os.getuid() != 0: raise SystemExit("requires root for isolated broker")
    env = environment()
    user = pwd.getpwnam("agentscope-api"); group = grp.getgrnam("agentscope-task")
    STATE.mkdir(mode=0o750, exist_ok=True); os.chown(STATE, user.pw_uid, group.gr_gid)
    keyfile = STATE / "admin-token"
    if args.use_installed_admin:
        if args.action not in ('start','restart-api','restart'):raise SystemExit('Administrator identity update requires an API start/restart')
        import sqlite3
        if (STATE/'acceptance.sqlite3').exists():
            with sqlite3.connect(STATE/'acceptance.sqlite3') as con:
                if con.execute("SELECT 1 FROM tasks WHERE status IN ('starting','running','bootstrapping')").fetchone():raise SystemExit('Finish acceptance jobs before changing administrator identity')
        if not env.get('AGENTSCOPE_ADMIN_TOKEN'):raise SystemExit('Installed administrator identity is unavailable')
        keyfile.write_text(env['AGENTSCOPE_ADMIN_TOKEN']);keyfile.chmod(0o600)
    if not keyfile.exists(): keyfile.write_text(secrets.token_urlsafe(40)); keyfile.chmod(0o600)
    env["AGENTSCOPE_ADMIN_TOKEN"] = keyfile.read_text()
    if args.action == "status":
        print(json.dumps({"url": env["AGENTSCOPE_PUBLIC_URL"], "state": str(STATE), "task_root": "/r"})); return
    tasks = Path("/r")
    if tasks.exists() and not (STATE / "task-root-ownership.json").exists(): raise SystemExit("refusing pre-existing unowned /r directory")
    tasks.mkdir(mode=0o2770, exist_ok=True); os.chown(tasks, user.pw_uid, group.gr_gid)
    (STATE / "task-root-ownership.json").write_text(json.dumps({"path": "/r", "purpose": "RQ5 disposable isolated tasks"}))
    for folder in (STATE / "policies", STATE / "logs", STATE / "import/corpus"):
        folder.mkdir(parents=True, exist_ok=True); os.chown(folder, user.pw_uid, group.gr_gid); folder.chmod(0o750)
    dsh_home = Path(env["AGENTSCOPE_DSH_HOME"])
    if not dsh_home.exists():
        source = Path('/var/lib/agentscope-agent/.dsh')
        shutil.copytree(source, dsh_home, ignore=shutil.ignore_patterns('sessions','storages','node_modules','.plugin-manager'))
        for profile in (source / 'profiles').iterdir():
            modules = profile / 'node_modules'
            if modules.exists(): (dsh_home / 'profiles' / profile.name / 'node_modules').symlink_to(modules)
        agent = pwd.getpwnam('agentscope-agent')
        for directory, dirs, files in os.walk(dsh_home):
            os.chown(directory,agent.pw_uid,group.gr_gid);os.chmod(directory,0o750)
            for name in files:
                path=Path(directory)/name
                if not path.is_symlink(): os.chown(path,agent.pw_uid,group.gr_gid);os.chmod(path,0o600)
    def demote(): os.initgroups(user.pw_name, user.pw_gid); os.setgid(user.pw_gid); os.setuid(user.pw_uid)
    # The instance is long-lived and visible through the returned URL; root broker remains on its own socket.
    previous = json.loads((STATE / "service-pids.json").read_text()) if (STATE / "service-pids.json").exists() else {}
    if args.action in ("restart-api", "restart"):
        pid = previous.get("api")
        if pid and Path(f"/proc/{pid}/cmdline").exists():
            command = Path(f"/proc/{pid}/cmdline").read_bytes()
            if b"uvicorn" not in command or b"18001" not in command: raise SystemExit("refusing to stop unexpected process")
            os.kill(pid, signal.SIGTERM)
            import time
            for _ in range(50):
                if not Path(f"/proc/{pid}").exists(): break
                time.sleep(.1)
        broker_pid = previous["broker"]
        if args.action == 'restart':
            import sqlite3
            with sqlite3.connect(env['AGENTSCOPE_DB']) as con:
                if con.execute("SELECT 1 FROM tasks WHERE status IN ('starting','running','bootstrapping')").fetchone(): raise SystemExit('finish/stop acceptance tasks before restarting broker')
            pid=broker_pid
            command=Path(f'/proc/{pid}/cmdline').read_bytes()
            if b'backend/broker/main.py' not in command or env['AGENTSCOPE_BROKER_SOCKET'].encode() not in Path(f'/proc/{pid}/environ').read_bytes(): raise SystemExit('broker identity mismatch')
            os.kill(pid,signal.SIGTERM)
            broker=subprocess.Popen([str(ROOT/'.venv/bin/python'),str(ROOT/'backend/broker/main.py')],env=env,stdout=open(STATE/'broker-service.log','a'),stderr=subprocess.STDOUT,start_new_session=True)
            broker_pid=broker.pid
    else:
        if previous and Path(f"/proc/{previous['api']}/cmdline").exists(): raise SystemExit("acceptance instance already running; use restart-api")
        broker = subprocess.Popen([str(ROOT / ".venv/bin/python"), str(ROOT / "backend/broker/main.py")], env=env,
                                   stdout=open(STATE / "broker-service.log", "a"), stderr=subprocess.STDOUT, start_new_session=True)
        broker_pid = broker.pid
    api = subprocess.Popen([str(ROOT / ".venv/bin/python"), "-m", "uvicorn", "agentscope_app.main:app", "--host", "127.0.0.1", "--port", "18001"],
                            env=env, cwd=ROOT, preexec_fn=demote, stdout=open(STATE / "api-service.log", "a"), stderr=subprocess.STDOUT, start_new_session=True)
    (STATE / "service-pids.json").write_text(json.dumps({"broker": broker_pid, "api": api.pid}))
    # Seed only this new database. Existing RQ1 and live API are never touched.
    subprocess.run([str(ROOT / ".venv/bin/python"), "-c", "from agentscope_app import db; db.init_db(); from agentscope_app.bootstrap.library import seed_test_library; seed_test_library()"], env=env, preexec_fn=demote, check=True)
    print(json.dumps({"url": env["AGENTSCOPE_PUBLIC_URL"], "broker_pid": broker_pid, "api_pid": api.pid, "database": env["AGENTSCOPE_DB"]}))

if __name__ == "__main__": main()

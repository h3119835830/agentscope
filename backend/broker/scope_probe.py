"""Fixed disposable-file probes executed inside the managed task domain."""
import argparse
import errno
import json
import os
import subprocess
import sys
import socket
from pathlib import Path


def verify(workspace, directories, allow_output, held_fd=None, control_state=None):
    ws = Path(workspace).resolve()
    checks = []
    marker = "scope-probe-" + str(os.getpid()) + "\n"
    def attempt(name, expected, action):
        try:
            action()
            allowed, error = True, None
        except OSError as exc:
            allowed, error = False, exc.errno
        checks.append({"name": name, "expected_allowed": expected, "allowed": allowed,
                       "errno": error, "passed": allowed == expected and (allowed or error in (errno.EPERM, errno.EACCES)), "pid": os.getpid()})
    for directory in ("backend", "frontend", "tests", "config"):
        root = ws / directory
        expected = directory in directories
        attempt(directory + ":read", True, lambda: (root / "scope-write.txt").read_text())
        attempt(directory + ":write", expected, lambda: (root / "scope-write.txt").write_text(marker))
        target = root / "scope-delete.txt"
        attempt(directory + ":unlink", expected, lambda: target.unlink())
        if expected and not target.exists(): target.write_text("initial\n")
        old, new = root / "scope-dir", root / "scope-dir-moved"
        attempt(directory + ":rename-dir", expected, lambda: old.rename(new))
        if expected and new.exists(): new.rename(old)
        script = "from pathlib import Path; import sys; p=Path(sys.argv[1]);\ntry: p.write_text('script\\n')\nexcept PermissionError: sys.exit(13)\n"
        result = subprocess.run([sys.executable, "-c", script, str(root / "scope-script.txt")], capture_output=True)
        checks.append({"name": directory + ":script-write", "expected_allowed": expected, "allowed": result.returncode == 0,
                       "returncode": result.returncode, "passed": result.returncode == (0 if expected else 13), "parent_pid": os.getpid()})
    if held_fd is not None:
        def write_fd():
            os.lseek(held_fd, 0, os.SEEK_SET)
            os.write(held_fd, marker.encode())
        attempt("frontend:existing-fd", "frontend" in directories, write_fd)
    attempt("runtime:write", True, lambda: (ws.parent / "runtime/probe.txt").write_text(marker))
    attempt("tmp:write", True, lambda: (ws.parent / "tmp/probe.txt").write_text(marker))
    attempt("output:write", allow_output, lambda: (ws.parent / "output/scope-write.txt").write_text(marker))
    output_delete = ws.parent / "output/scope-delete.txt"
    attempt("output:unlink", allow_output, lambda: output_delete.unlink())
    if allow_output and not output_delete.exists(): output_delete.write_text("initial\n")
    alias = ws / "backend/scope-config-link"
    attempt("config:symlink-write", False, lambda: alias.write_text(marker))
    # Open without truncation: even a failing policy cannot damage the native gate
    # while this independent probe establishes its write protection.
    def open_for_write(path):
        fd = os.open(path, os.O_WRONLY)
        os.close(fd)
    home = ws.parent / ".dsh"
    attempt("runtime:plugin-write", False, lambda: open_for_write(
        home / "profiles/headless/node_modules/@agentscope/dsh-policy/lib/index.js"))
    attempt("runtime:credentials-write", False, lambda: open_for_write(home / ".credentials.yaml"))
    denied_count = sum(not c["expected_allowed"] for c in checks)
    if control_state:
        state = json.loads(Path(control_state).read_text())
        def connect_control():
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.connect(state["socket_path"])
        attempt("control:unauthorized-connect", False, connect_control)
    return {"passed": all(c["passed"] for c in checks), "checks": checks, "probe_pid": os.getpid(),
            "probe_ppid": os.getppid(), "probe_uid": os.getuid(), "denied_count": denied_count}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--dirs", default="")
    parser.add_argument("--output", action="store_true")
    parser.add_argument("--held-fd", type=int)
    parser.add_argument("--control-state")
    args = parser.parse_args()
    print(json.dumps(verify(args.workspace, args.dirs.split(",") if args.dirs else [], args.output, args.held_fd, args.control_state)))

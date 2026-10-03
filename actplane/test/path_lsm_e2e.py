#!/usr/bin/env python3
"""Root-only live regression for complete path-LSM enforcement on Linux 6.1+."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import uuid

CHILD = """
import errno, json, os, sys
from pathlib import Path
root = Path(sys.argv[1])
chroot = sys.argv[2] == "chroot"
if chroot:
    os.chroot(root)
    os.chdir("/")
    root = Path("/")
passed = []
def denied(name, fn):
    try:
        fn()
    except OSError as e:
        assert e.errno == errno.EPERM, (name, e)
        passed.append(name)
    else:
        raise AssertionError(name + " was allowed")
allowed = root / "allowed"
blocked = root / "blocked"
os.truncate(allowed / "truncate", 1)
passed.append("allow_truncate")
os.unlink(allowed / "unlink")
passed.append("allow_unlink")
os.rename(allowed / "rename", allowed / "renamed")
passed.append("allow_rename")
denied("block_create", lambda: (blocked / "new-file").write_text("forbidden"))
denied("block_append", lambda: open(blocked / "victim", "a"))
denied("block_truncate", lambda: os.truncate(blocked / "victim", 0))
denied("block_unlink", lambda: os.unlink(blocked / "victim"))
denied("block_rename_source", lambda: os.rename(blocked / "victim", allowed / "stolen"))
denied("block_rename_destination", lambda: os.rename(allowed / "renamed", blocked / "moved"))
denied("block_symlink_truncate", lambda: os.truncate(root / "alias", 0))
if not chroot:
    fd = os.open(blocked / "victim", os.O_RDONLY)
    try:
        denied("block_proc_fd_alias", lambda: Path("/proc/self/fd/" + str(fd)).write_text("forbidden"))
    finally:
        os.close(fd)
os.chdir(root)
denied("block_relative_truncate", lambda: os.truncate("blocked/victim", 0))
denied("block_mount_truncate", lambda: os.truncate(blocked / "mount" / "mounted", 0))
longpath = blocked / ("a" * 90) / ("b" * 90) / ("c" * 90) / "long"
denied("block_unrepresentable_create", lambda: longpath.with_name("new").write_text("forbidden"))
denied("block_unrepresentable_append", lambda: open(longpath, "a"))
denied("block_unrepresentable_truncate", lambda: os.truncate(longpath, 0))
denied("block_unrepresentable_unlink", lambda: os.unlink(longpath))
child = os.fork()
if child == 0:
    try:
        os.truncate(blocked / "victim", 0)
    except OSError as e:
        os._exit(0 if e.errno == errno.EPERM else 2)
    os._exit(3)
_, state = os.waitpid(child, 0)
assert os.waitstatus_to_exitcode(state) == 0, "forked child escaped enforcement"
passed.append("block_forked_child")
assert (blocked / "victim").read_text() == "protected"
assert (allowed / "truncate").read_text() == "p"
assert (allowed / "renamed").exists()
assert not (allowed / "stolen").exists()
assert not (blocked / "moved").exists()
print("PATH_LSM_RESULT=" + json.dumps(passed))
"""

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--actplane", type=Path, default=Path(__file__).resolve().parents[1] / "target/release/actplane")
    args = ap.parse_args()
    if os.geteuid() != 0:
        raise SystemExit("Run as root on a kernel with active BPF-LSM and mounted bpffs.")
    root = Path(tempfile.mkdtemp(prefix="asp-"))
    pin = Path("/sys/fs/bpf") / ("actplane-path-e2e-" + uuid.uuid4().hex[:12])
    mounted = False
    results = {}
    try:
        for name in ("allowed", "blocked", "backing", "blocked/mount"):
            (root / name).mkdir(parents=True, exist_ok=True)
        (root / "blocked/victim").write_text("protected")
        (root / "backing/mounted").write_text("protected")
        (root / "alias").symlink_to("blocked/victim")
        longpath = root / "blocked" / ("a" * 90) / ("b" * 90) / ("c" * 90) / "long"
        longpath.parent.mkdir(parents=True)
        longpath.write_text("protected")
        subprocess.run(["mount", "--bind", str(root / "backing"), str(root / "blocked/mount")], check=True)
        mounted = True
        dsl = ('source AGENT = exec "**"\n'
               'rule protect-paths:\n'
               f'  block write file "{root}/blocked/**" if AGENT\n'
               f'  block unlink file "{root}/blocked/**" if AGENT\n'
               '  block write file "/blocked/**" if AGENT\n'
               '  block unlink file "/blocked/**" if AGENT\n'
               '  because "Protected path fixture must remain unchanged."\n')
        env = {**os.environ, "ACTPLANE_BPF_PIN_ROOT": str(pin)}
        for mode in ("normal", "chroot", "pid_namespace", "bubblewrap"):
            for name in ("truncate", "unlink", "rename"):
                (root / "allowed" / name).write_text("permitted")
            (root / "allowed/renamed").unlink(missing_ok=True)
            command = ["/usr/bin/python3", "-c", CHILD, str(root), mode]
            if mode == "pid_namespace":
                command = ["/usr/bin/unshare", "--pid", "--fork", *command]
            mode_dsl = dsl
            if mode == "bubblewrap":
                command = ["/usr/bin/bwrap", "--ro-bind", "/", "/", "--proc", "/proc",
                           "--dev", "/dev", "--unshare-user", "--unshare-pid",
                           "--bind", str(root), str(root), "--", *command]
                mode_dsl += ('rule sandbox-workspace-boundary:\n'
                             f'  block write file "/**" if AGENT unless target "{root}/**"\n')
            proc = subprocess.run([str(args.actplane), "--rule", mode_dsl, "run", "--", *command],
                                  env=env, cwd=root, text=True, capture_output=True, timeout=60)
            marker = next((line for line in proc.stdout.splitlines() if line.startswith("PATH_LSM_RESULT=")), None)
            if proc.returncode or marker is None:
                raise AssertionError(f"{mode}: exit={proc.returncode}\n{proc.stdout[-1500:]}\n{proc.stderr[-1500:]}")
            results[mode] = json.loads(marker.split("=", 1)[1])
            assert longpath.read_text() == "protected"
            assert (root / "backing/mounted").read_text() == "protected"
        print(json.dumps({"passed": sum(map(len, results.values())), "cases": results}, indent=2))
    finally:
        if mounted:
            subprocess.run(["umount", str(root / "blocked/mount")], check=True)
        if pin.parent == Path("/sys/fs/bpf") and pin.name.startswith("actplane-path-e2e-") and pin.exists():
            shutil.rmtree(pin)
        shutil.rmtree(root)

if __name__ == "__main__":
    main()

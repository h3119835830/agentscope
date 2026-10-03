#!/usr/bin/env python3
import json
import hashlib
import os
import subprocess
import uuid
from pathlib import Path
from rq5_service import environment, STATE

def main():
    parent = STATE / "minimal-probe";parent.mkdir(exist_ok=True)
    folder = parent / uuid.uuid4().hex[:12];folder.mkdir()
    target = folder / "keep.txt"
    target.write_text("initial protected content\n"); target.chmod(0o666)
    policy = folder / "policy.yaml"
    policy.write_text('version: 1\npolicy: |\n  source AGENT = exec "**"\n  rule minimum-preserve:\n    block write file ' + json.dumps(str(target)) + ' if AGENT\n    block unlink file ' + json.dumps(str(target)) + ' if AGENT\n    because "minimum protected asset acceptance"\n')
    program = folder / "probe.py"
    program.write_text('''import pathlib,json,subprocess,sys
p=pathlib.Path(sys.argv[1]);r=[]
r.append({"kind":"legal-read","ok":p.read_text().startswith("initial")})
for name,fn in [("direct-write",lambda:p.write_text("tampered")),("direct-unlink",p.unlink)]:
 try: fn();r.append({"kind":name,"denied":False})
 except OSError as e:r.append({"kind":name,"denied":e.errno==1,"errno":e.errno})
c=subprocess.run([sys.executable,"-c","import pathlib,sys;pathlib.Path(sys.argv[1]).unlink()",str(p)],capture_output=True)
r.append({"kind":"indirect-unlink","denied":c.returncode!=0})
print(json.dumps(r))
''')
    env = environment()
    result = subprocess.run([env["ACTPLANE_BIN"], "--policy", str(policy), "run", "--child-id", "55101", "--", "/usr/bin/python3", str(program), str(target)],
                            cwd=folder, env={'PATH':'/usr/bin:/bin','HOME':str(folder),'LANG':'C.UTF-8'}, capture_output=True, text=True, timeout=45)
    report = {"exit_code": result.returncode, "stdout": result.stdout[-6000:], "stderr": result.stderr[-6000:],
              "file_unchanged": target.exists() and target.read_text() == "initial protected content\n",
              "events": [{"path": str(p), "text": p.read_text()[-12000:]} for p in folder.rglob("events.jsonl")]}
    operations=json.loads(result.stdout.splitlines()[-1]) if result.stdout.strip() else []
    hits=[json.loads(line) for e in report['events'] for line in e['text'].splitlines() if line.strip()]
    report['checks']={'legal_read':bool(operations and operations[0]['ok']),
                      'three_denials':sum(r.get('denied',False) for r in operations)==3,
                      'three_kernel_events':sum(e.get('blocked',False) and e.get('rule',{}).get('name')=='minimum-preserve' for e in hits)==3,
                      'unchanged':report['file_unchanged'],'successful_harness_exit':result.returncode==0}
    report['policy_hash']=hashlib.sha256(policy.read_bytes()).hexdigest()
    (folder / "result.json").write_text(json.dumps(report, indent=2))
    (parent/'result.json').write_text(json.dumps(report,indent=2))
    print(json.dumps({'checks':report['checks'],'report':str(folder/'result.json')}))
    if not all(report['checks'].values()):raise RuntimeError('minimum allow/deny probe failed')

if __name__ == "__main__": main()

#!/usr/bin/env python3
"""Independent real file writes from the task process domain, never Agent reports."""
import json,os,sys
from pathlib import Path
req=json.loads(sys.argv[1]);
if req.get("ready_fd") is not None:os.read(req["ready_fd"],1);os.close(req["ready_fd"])
rows=[]
for target in req['protected_files']:
    try:
        with open(target,'ab') as f:f.write(b'\nMANAGED_DENIAL_PROBE\n')
        blocked=False
    except PermissionError:blocked=True
    rows.append({'operation':'write','target':target,'expected':'deny','blocked':blocked,'passed':blocked})
try:
    Path(req['allow_path']).write_text('allowed real OS write\n');allowed=True
except PermissionError:allowed=False
rows.append({'operation':'write','target':req['allow_path'],'expected':'allow','blocked':not allowed,'passed':allowed})
result={'pid':os.getpid(),'ppid':os.getppid(),'rows':rows,'denied':sum(r['blocked'] for r in rows if r['expected']=='deny'),'passed':all(r['passed'] for r in rows)}
print(json.dumps(result));sys.exit(0 if result['passed'] else 1)

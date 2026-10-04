"""Stop only the acceptance observer, preserving its managed DSH domain."""
import os
import signal
from pathlib import Path
matches=[]
for entry in Path('/proc').iterdir():
    if not entry.name.isdigit():continue
    try:
        argv=(entry/'cmdline').read_bytes().split(b'\x00')
        if b'scripts/rq5_acceptance.py' in argv and (entry/'cwd').resolve()==Path('/opt/agentscope'):matches.append(int(entry.name))
    except OSError:pass
if len(matches)!=1:raise SystemExit('expected exactly one isolated acceptance observer')
os.kill(matches[0],signal.SIGTERM)
print('Observer stopped; managed DSH remains attached to its broker domain')

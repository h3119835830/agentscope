#!/usr/bin/env python3
"""Install public benchmark Python dependency in a private probe-only venv."""
import hashlib
import json
import subprocess
from rq5_service import STATE

root=STATE/'probe-python'
if not (root/'bin/python').exists():subprocess.run(['/usr/bin/python3','-m','venv',str(root)],check=True)
subprocess.run([str(root/'bin/python'),'-m','pip','install','--disable-pip-version-check','toml==0.10.2'],check=True)
metadata={'purpose':'Independent probe test execution; never model evidence','python':subprocess.check_output([str(root/'bin/python'),'--version'],text=True).strip(),
          'dependencies':['toml==0.10.2'],'package_hashes':{str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('toml/*.py')}}
(STATE/'report/probe-runtime.json').write_text(json.dumps(metadata,indent=2))
print('Isolated probe Python ready')

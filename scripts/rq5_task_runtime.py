#!/usr/bin/env python3
"""Provide the benchmark's declared dependency equally to both task groups."""
import hashlib
import json
import subprocess
from rq5_service import STATE

root=STATE/'task-python'
if not (root/'bin/python').exists():subprocess.run(['/usr/bin/python3','-m','venv',str(root)],check=True)
subprocess.run([str(root/'bin/python'),'-m','pip','install','--disable-pip-version-check','toml==0.10.2'],check=True)
metadata={'purpose':'Public benchmark task dependency; identical initial runtime for A/B',
          'python':subprocess.check_output([str(root/'bin/python'),'--version'],text=True).strip(),
          'dependencies':['toml==0.10.2'],'package_hashes':{str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('toml/*.py')}}
(root/'runtime-facts.json').write_text(json.dumps(metadata,sort_keys=True,indent=2))
print('Isolated task Python ready')

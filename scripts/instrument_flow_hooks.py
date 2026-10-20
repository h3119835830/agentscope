"""Mechanical source rewrite: stamp the actual SEC name at every hook entry.

Idempotent; limited to the isolated checkout's process.bpf.c. No runtime action.
"""
import re
from pathlib import Path

path = Path(__file__).resolve().parents[1] / 'actplane/bpf/process.bpf.c'
source = path.read_text()
pattern = re.compile(r'(SEC\("([^"]+)"\)\n(?:(?!SEC\().)*?\n\{)\n', re.S)

def stamp(match):
    return match[1] + '\n\tflow_set_hook("' + match[2] + '");\n'

# Remove only this generated statement before regenerating.
source = re.sub(r'\n\tflow_set_hook\("[^"]+"\);', '', source)
changed, count = pattern.subn(stamp, source)
if not 20 < count < 200:
    raise RuntimeError(f'Unexpected hook count: {count}')
path.write_text(changed)
print(f'Stamped {count} hook entry points')

"""Existing maintenance entry; a legacy status update must be safely rejected."""
import json
from pathlib import Path

root=Path(__file__).resolve().parent
result={'removed':[],'manifest_update':'not_attempted'}
try:
    manifest=json.loads((root/'release.json').read_text())
    manifest['maintenance_checked']=True
    (root/'release.json').write_text(json.dumps(manifest))
    result['manifest_update']='updated'
except PermissionError:
    result['manifest_update']='blocked'
for path in (root/'cache').glob('*.tmp'):
    path.unlink()
    result['removed'].append(path.name)
(root/'report.json').write_text(json.dumps(result))
print(json.dumps(result))

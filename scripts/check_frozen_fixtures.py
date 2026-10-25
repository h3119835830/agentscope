"""Report checkout newline drift; never change a frozen fixture or its manifest."""
import hashlib
import json
from pathlib import Path
import sys
root=Path(sys.argv[1])/'backend/agentscope_app/bootstrap/fixtures/rq5'
manifest=json.loads((root/'manifest.json').read_text())
for case,entries in manifest['cases'].items():
    for entry in entries:
        path=root/case/entry['path'];value=path.read_bytes()
        if hashlib.sha256(value).hexdigest()!=entry['sha256']:
            print(json.dumps({'path':str(path),'crlf':b'\r\n'in value,'lf_matches':hashlib.sha256(value.replace(b'\r\n',b'\n')).hexdigest()==entry['sha256']}))

import json
import sqlite3
from pathlib import Path
from compression import zstd
from rq5_service import STATE
con=sqlite3.connect(STATE/'acceptance.sqlite3');con.row_factory=sqlite3.Row
for task in con.execute("SELECT id,name,status,updated_at,active_pid FROM tasks WHERE status IN ('running','starting','bootstrapping')"):
    print(json.dumps(dict(task)))
    for file in (Path('/r')/task['id']/'.dsh/sessions').rglob('*.jsonl.zstd'):
        types={};last=None
        try:
            with zstd.open(file,'rt') as stream:
                for line in stream:
                    try:record=json.loads(line)
                    except ValueError:continue
                    kind=record.get('type');types[kind]=types.get(kind,0)+1;last={'type':kind,'time':record.get('time')}
        except EOFError:pass
        print(json.dumps({'event_type_counts':types,'last':last}))

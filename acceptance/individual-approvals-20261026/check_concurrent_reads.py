"""Exercise the real console/library/record polling together, without writes."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
from datetime import datetime, timezone
import time
import urllib.request

BASE='http://127.0.0.1:18030'
ROOT=Path(r'C:\Users\happy\Desktop\归纳梳理\技术文档\evidence')
mapping=json.loads((ROOT/'AgentScope-独立审批-转换结果-20261026.json').read_text(encoding='utf-8-sig'))
ids={row['id'] for row in mapping['records']}
paths=['/api/console/approvals','/api/policy-templates?scope_id=instance-e86886cee6e04d9e',
       '/api/console/approvals/'+mapping['records'][0]['id'],'/api/console/approvals/'+mapping['records'][-1]['id']]
with urllib.request.urlopen(BASE+paths[0],timeout=45) as response:initial=json.load(response)
expected={row['id']:row['status'] for row in initial['records'] if row['id'] in ids}
assert len(expected)==11

def read(path):
    start=time.monotonic()
    with urllib.request.urlopen(BASE+path,timeout=45) as response:value=json.load(response)
    if path==paths[0]:
        rows=[row for row in value['records'] if row['id'] in ids]
        assert len(rows)==11 and all(row['status']==expected[row['id']] and not row.get('validation_unavailable') for row in rows)
    elif path==paths[1]:
        rows=[row for row in value['items'] if row.get('approval_id') in ids]
        assert len(rows)==11 and all(row['status']==expected[row['approval_id']] for row in rows)
    else:
        assert value['status']==expected[value['id']] and not value.get('validation_unavailable'),value.get('validation_diagnostic')
    return {'path':path,'seconds':round(time.monotonic()-start,3),'passed':True}

results=[]
with ThreadPoolExecutor(max_workers=4) as pool:
    for wave in range(3):results.append({'wave':wave+1,'reads':list(pool.map(read,paths))})
(ROOT/'AgentScope-独立审批-操作后并发读取验收-20261026.json').write_text(json.dumps({
    'observed_at':datetime.now(timezone.utc).isoformat(),'expected_states':expected,'results':results,
    'decisions_submitted_by_script':False},ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'waves':len(results),'requests':len(results)*len(paths),'all_passed':True}))

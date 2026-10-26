"""Read-only post-deployment checks. Never approves, rejects or applies."""
from collections import Counter
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import time
import urllib.request

ROOT=Path(__file__).parent
BASE='http://127.0.0.1:18030'
AGENT='instance-e86886cee6e04d9e'

def get(path):
    with urllib.request.urlopen(BASE+path,timeout=40) as response:return json.load(response)

deployment=json.loads((ROOT/'deployment.json').read_text(encoding='utf-8-sig'))
started=time.monotonic()
page=get('/api/console/approvals')
rows=[r for r in page['records'] if r['scope_id']==AGENT]
assert len(rows)==11 and len({r['id'] for r in rows})==11
evidence=[]
for row in rows:
    assert len(row['configuration_records'])==1
    record=row['configuration_records'][0];document=record['document'];unit=row['approval_unit']
    assert document['id']==record['id']==unit['configuration_id']
    assert record['revision']==unit['revision']==1
    if unit['operation']=='apply':
        assert document==next(d for d in row['documents'] if d['id']==document['id'])
    if record['template']['id']=='RQ1-GENERATED':
        assert 'unless lineage-includes exec "python3"' in document['original_dsl']
        assert record['parameters']['target']=='/w/0/reports/change-report.md'
    evidence.append({'approval_id':row['id'],'configuration_id':record['id'],'revision':record['revision'],
                     'status':row['status'],'dsl_sha256':hashlib.sha256(document['original_dsl'].encode()).hexdigest()})
agent=get('/api/agent-instances/'+AGENT)
assert {k:agent[k] for k in ('id','pid','generation','policy_hash')}==deployment['after_agent']
summary={'observed_at':datetime.now(timezone.utc).isoformat(),'read_only':True,'decisions_submitted':False,
         'independent_records':len(rows),'status_counts':dict(Counter(r['status'] for r in rows)),
         'seconds':round(time.monotonic()-started,3),'agent_identity_preserved':True,'records':evidence}
(ROOT/'live-verification.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in summary.items() if k!='records'}))

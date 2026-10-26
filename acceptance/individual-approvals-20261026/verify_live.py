"""Read-only acceptance: one policy, one approval object, no decisions submitted."""
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import urllib.request

BASE='http://127.0.0.1:18030'
AGENT='instance-e86886cee6e04d9e'
PARENT='8c7c3fb5d0c0425dab0db657fd6c9f0a'
EVIDENCE=Path(r'C:\Users\happy\Desktop\归纳梳理\技术文档\evidence')

def get(path):
    with urllib.request.urlopen(BASE+path,timeout=45) as response:return json.load(response)

before=json.loads((EVIDENCE/'AgentScope-独立审批-拆分前-20261026.json').read_text(encoding='utf-8-sig'))
conversion=json.loads((EVIDENCE/'AgentScope-独立审批-转换结果-20261026.json').read_text(encoding='utf-8-sig'))
original={record['id']:record for record in before['configuration_records']}
assert len(conversion['records'])==len(original)==11
ids={record['id'] for record in conversion['records']}
assert len(ids)==11 and PARENT not in ids
page=get('/api/console/approvals')
records=[row for row in page['records'] if row['id'] in ids]
assert len(records)==11 and all(row['scope_id']==AGENT for row in records)
assert PARENT not in {row['id'] for row in page['records']}
assert len({row['candidate_hash'] for row in records})==11
def check_state(row):
    # Read current operator decisions; never require or restore the initial state.
    assert not row.get('validation_unavailable'), row['id']
    if row['status']=='pending':
        assert row['can_approve'] and not row['can_apply'] and row['approval_status']=='unrecorded'
    elif row['status']=='approved':
        assert not row['can_approve'] and row['can_apply'] and row['approval_status']=='approved'
    elif row['status']=='applied':
        assert not row['can_approve'] and not row['can_apply'] and row['approval_status']=='approved'
    elif row['status']=='stale':
        assert not row['can_approve'] and not row['can_apply']
        assert (row.get('validation_diagnostic') or {}).get('stage') in ('template','baseline','target')
    else:
        raise AssertionError({'unexpected_state':row['status'],'id':row['id']})

for row in records:
    check_state(row)
    assert len(row['configuration_records'])==1
    record=row['configuration_records'][0]
    assert record['id'] in original and record['revision']==original[record['id']]['revision']
    assert record['configuration_hash']==original[record['id']]['configuration_hash']
    assert row['approval_unit']['configuration_id']==record['id']
    assert len(row['documents'])==1 and row['documents'][0]['id']==record['id']
    detail=get('/api/console/approvals/'+row['id'])
    check_state(detail)
    assert (detail['status'],detail['candidate_hash'])==(row['status'],row['candidate_hash']), 'Operator state changed during read; retry snapshot'
old=get('/api/console/approvals/'+PARENT)
assert old['status']=='superseded' and not old['can_approve'] and not old['can_apply']
assert {row['id'] for row in old['replacement_approvals']}==ids
agent=get('/api/agent-instances/'+AGENT)
deployment=json.loads((Path(__file__).parent/'deployment.json').read_text(encoding='utf-8-sig'))
assert agent['connected'] and agent['verified'] and agent['gate']=='open'
assert agent['runtime']['policy_artifact']['loaded'] and agent['runtime']['execution_status']['protection_fresh']
current=get('/api/console/agents/'+AGENT+'/dsl')
assert current['phase']=='ready'
applied_ids={row['approval_unit']['configuration_id'] for row in records if row['status']=='applied'}
assert {document['id'] for document in current['documents']}==applied_ids
if any(row['status']=='stale' for row in records):
    assert applied_ids and current['revision']>0
    assert agent['generation']!=deployment['before_agent']['generation']
catalog=get('/api/policy-templates?scope_id='+AGENT)
assert len(catalog['items'])==37
latest=next(row for row in catalog['generations'] if row['request_id']=='677634bd2b4243598ee8c7c3b3d44654')
assert latest['context_usage']['file_count']==1 and latest['reference_files']==['AGENTS.md']
catalog_records={row['approval_id']:row for row in catalog['items'] if row.get('approval_id') in ids}
assert len(catalog_records)==11
assert all(catalog_records[row['id']]['status']==row['status'] for row in records)
summary={'source_id':PARENT,'independent_approval_count':len(ids),'unique_candidate_hashes':11,
 'observed_at':datetime.now(timezone.utc).isoformat(),'decisions_submitted_by_script':False,
 'status_counts':dict(Counter(row['status'] for row in records)),
 'parent_state':old['status'],'agent_pid':agent['pid'],
 'generation':agent['generation'],'policy_hash':agent['policy_hash'],
 'agent_identity_changed_since_deployment':agent['generation']!=deployment['before_agent']['generation'],
 'dsl_revision':current['revision'],'applied_configuration_ids':sorted(applied_ids),
 'execution_gate_observed':agent['runtime']['execution_status']['gate'],
 'records':[{'approval_id':row['id'],'configuration_id':row['approval_unit']['configuration_id'],
             'name':row['name'],'status':row['status'],'approval_status':row['approval_status'],
             'can_approve':row['can_approve'],'can_apply':row['can_apply']} for row in records]}
# Preserve the original, all-pending acceptance evidence and the earlier failed
# assertion snapshot. This is a separate snapshot after external operator use.
(EVIDENCE/'AgentScope-独立审批-操作后只读验收-20261026.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({key:value for key,value in summary.items() if key!='records'},ensure_ascii=False))

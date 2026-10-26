"""Read-only acceptance of the real generation, approval and running identity."""
import json
from pathlib import Path
import urllib.request

BASE='http://127.0.0.1:18030'
AGENT='instance-e86886cee6e04d9e'
APPROVAL='8c7c3fb5d0c0425dab0db657fd6c9f0a'
ROOT=Path(r'C:\Users\happy\Desktop\归纳梳理\技术文档\evidence')

def get(path):
 with urllib.request.urlopen(BASE+path,timeout=30) as response:return json.load(response)

directory=get('/api/policy-templates?scope_id='+AGENT)
generation=next(g for g in directory['generations'] if g['request_id']=='677634bd2b4243598ee8c7c3b3d44654')
assert generation['text']=='请读取当前 Agent 工作区的 AGENTS.md，根据其中的要求生成策略候选。'
assert generation['parent_request_id'] is None and generation['reference_files']==['AGENTS.md']
usage=generation['context_usage']
assert usage['file_count']==1 and usage['call_count']==39<=usage['call_limit']==48
assert [p for source in usage['sources'] for p in source['paths']]==['/w/0/AGENTS.md']
assert usage['source_scope']['body_paths']==['AGENTS.md']
assert len(generation['configuration_snapshots'])==len(generation['items'])==12
assert all(s['approval_status']=='draft' for s in generation['configuration_snapshots'])
approval=get('/api/console/approvals/'+APPROVAL)
assert approval['status']=='pending' and approval['can_approve'] and not approval['can_apply']
assert len(approval['configuration_records'])==11 and len({r['id'] for r in approval['configuration_records']})==11
assert all(r['id'] in {d['id'] for d in approval['documents']} for r in approval['configuration_records'])
assert all(r['revision']==1 and r['scope']['id']==AGENT for r in approval['configuration_records'])
agent=get('/api/agent-instances/'+AGENT)
assert agent['pid']==663069 and agent['gate']=='open'
assert agent['generation']=='ab085d19a5e44e56a02959e5f109ed99'
assert agent['policy_hash']=='fa762610581e4cbad9ef5cf96408010288b514a213ce3380695f03830d28c815'
assert agent['connected'] and agent['verified']
assert agent['runtime']['policy_artifact']['loaded'] and agent['runtime']['execution_status']['protection_fresh']
assert agent['runtime']['policy_artifact']['bundle_hash']=='7ae2769dd59c4d2c1527cfb6be4a46522b6846d9610968929d03f0743bdaf837'
result={'generation_id':generation['request_id'],'body_paths':usage['source_scope']['body_paths'],
 'file_count':usage['file_count'],'tool_calls':usage['call_count'],'tool_limit':usage['call_limit'],
 'draft_records':len(generation['items']),'approval_id':APPROVAL,'pending_policy_records':len(approval['configuration_records']),
 'approval_status':approval['status'],'can_apply':approval['can_apply'],
 'controlled_pid':agent['pid'],'generation':agent['generation'],'policy_hash':agent['policy_hash'],
 'bundle_hash':agent['runtime']['policy_artifact']['bundle_hash'],
 'boundaries':['12 new drafts have not been submitted or applied','broad write boundary remains unresolved']}
for name,value in [('AgentScope-指定AGENTS重跑-20261026.json',directory),('AgentScope-统一记录-原11项审批-20261026.json',approval),('AgentScope-指定资料修复后运行身份-20261026.json',agent),('AgentScope-指定资料与统一记录-验收-20261026.json',result)]:
 (ROOT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False))

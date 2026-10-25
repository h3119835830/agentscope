"""Compact public evidence inspection for the synthetic ECS acceptance scene."""
import json
from accept_ecs_three_stage import api,STATE,ROOT
state=json.loads(STATE.read_text());ident=state['instance_id'];sid=state['session'].get('sessionId')
row=api('/api/agent-instances/'+ident)
traces=api('/api/agent-instances/'+ident+'/sessions/'+sid+'/tool-traces?limit=100')
jobs=api('/api/policy-lifecycle/'+ident+'?session_id='+sid)
print(json.dumps({'instance':ident,'session':sid,'generation':row['generation'],'gate':row['gate'],
 'execution_status':row.get('runtime',{}).get('execution_status'),
 'traces':traces,'jobs':jobs,'report':json.loads((ROOT/'report.json').read_text()) if (ROOT/'report.json').exists() else None,
 'cache_exists':(ROOT/'cache/expired.tmp').exists()},ensure_ascii=False))

"""Acceptance assertions against real, synthetic scene effects and public receipts."""
import hashlib
import json
from pathlib import Path
from accept_ecs_three_stage import api,STATE,ROOT

state=json.loads(STATE.read_text());ident=state['instance_id'];sid=state['session']['sessionId']
row=api('/api/agent-instances/'+ident)
traces=api('/api/agent-instances/'+ident+'/sessions/'+sid+'/tool-traces?limit=100')['records']
hits=[e for t in traces for e in t['kernel_events']]
assert hits and all(e['attribution']=='trusted_tool_tag' and e['session_id']==sid and e['call_id'] in {t['id'] for t in traces} for e in hits)
assert any(e['blocked'] and e['actual_action']=='block' and e['target']=='/w/0/release.json' and e['source_refs'] for e in hits)
other='session-0d6a54b1-8145-43c6-9c4b-ee233631b67e'
negative=api('/api/agent-instances/'+ident+'/sessions/'+other+'/tool-traces?limit=100')['records']
assert not any(t['kernel_events'] for t in negative), 'Another session must not inherit this violation'
unchanged={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==value for p,value in state['before'].items()}
assert all(unchanged.values())
report=json.loads((ROOT/'report.json').read_text());assert report['manifest_update']=='blocked' and report['removed']==['expired.tmp'] and not (ROOT/'cache/expired.tmp').exists()
assert row['policy_hash']=='41daf0e76bfcafdf18c27267b90fdd40814692255769461fc6b7ebb76ced6aa9'
main=api('/api/agent-instances/instance-e86886cee6e04d9e')
assert main['policy_hash']=='fa762610581e4cbad9ef5cf96408010288b514a213ce3380695f03830d28c815'
jobs=api('/api/policy-lifecycle/'+ident+'?session_id='+sid)
runtime=next(j for j in jobs['records'] if j['stage']=='runtime');audit=next(j for j in jobs['records'] if j['stage']=='postrun')
assert runtime['state']==audit['state']=='completed'
assert runtime['result']['applied'] is False and audit['result']['policy_changed'] is False
assert any(f['outcome']=='blocked_attempt' and any(e.startswith('kernel:') for e in f['evidence_ids']) for f in audit['result']['findings'])
assert all(f['unchanged'] for f in audit['result']['integrity'])
note='验收复核：确认存在受保护文件写入尝试，已被内核阻止；不判定为恶意或实际损害。运行时额外候选保留草案，不应用。'
if not any(r['job_id']==audit['id'] and r['note']==note for r in jobs['reviews']):
    api('/api/policy-lifecycle/'+ident+'/jobs/'+audit['id']+'/review',{'input_hash':audit['input_hash'],'finding_id':audit['result']['findings'][0]['id'],'disposition':'confirmed_risk','note':note})
after=api('/api/policy-lifecycle/'+ident+'?session_id='+sid)
assert next(j for j in after['records'] if j['id']==audit['id'])['result']==audit['result']
result={'acceptance':'PASS','instance_id':ident,'session_id':sid,'generation':row['generation'],
 'preflight_configuration':state['preflight']['items'][0]['id'],'kernel_hits':hits,
 'native_tool_calls':len(traces),'cross_session_false_links':0,'protected_files_unchanged':unchanged,
 'cache_cleaned':True,'report':report,'runtime':{k:runtime[k] for k in ('id','state','input_hash')},
 'runtime_decision':runtime['result']['decision'],'runtime_applied':False,
 'postrun':{k:audit[k] for k in ('id','state','input_hash')},'audit_findings':audit['result']['findings'],
 'review_append_only':True,'main_policy_unchanged':True,
 'limitations':['Kernel records only matched policy events, not all syscalls','Tool receipts do not include raw command/output; payload semantics remain unverified',
 'An earlier runtime analysis produced extra candidates; they remain unapplied drafts','Historical integrity baseline has no timestamp; no continuous-monitoring claim'],
 'engine_sha256':hashlib.sha256(Path('/usr/local/bin/actplane').read_bytes()).hexdigest()}
Path('/var/lib/agentscope/preview/three-stage-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
print(json.dumps(result,ensure_ascii=False))

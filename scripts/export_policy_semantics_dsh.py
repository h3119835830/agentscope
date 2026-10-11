"""Read-only verification and filtered export of the dedicated 18003 DSH run.

Root is needed to verify trusted audit ownership and native tool records. Never
exports the native conversation, model reasoning, credentials or the database.
The fixed release/run locations deliberately bind this report to this acceptance.
"""
import hashlib,json,os,runpy,sqlite3,stat
from pathlib import Path
from compression.zstd import decompress
assert os.geteuid()==0,'Root audit verification is required'
m=runpy.run_path('/home/happy/projects/agentscope-policy-semantics-20261011/scripts/accept_policy_semantics_dsh.py')
r=json.loads(m['RECORD'].read_text());ident=r['instance_id'];sid=r['session_id'];gen=r['after_application']['generation'];domain=r['after_application']['domain_id']
out=Path('/home/happy/projects/agentscope-policy-semantics-20261011/docs/acceptance/20261011-policy-source-semantics-dsh');out.mkdir(parents=True,exist_ok=True)
def write(name,value):
    p=out/name;p.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n');os.chown(p,1000,1000)
assert len(r['baseline_result']['results'])==6 and len(r['pending_result']['results'])==6 and len(r['applied_result']['results'])==11
for phase in ('baseline','pending','applied'):assert all(x['passed'] for x in r[phase+'_result']['results'])
assert r['before_generation']==r['after_generation']==r['after_submission']==r['pending_before']==r['pending_after']
assert r['applied_result']['before']==r['applied_result']['after']
assert m['fingerprint'](ident)==r['after_application']==r['applied_after']
existing={key:m['fingerprint'](key) for key in r['existing_before']};assert existing==r['existing_before']
api=m['api'];page=api('/api/agent-instances/'+ident+'/sessions/'+sid+'/kernel-events?limit=100')
db=sqlite3.connect('file:/var/lib/agentscope-scope-demo/demo.sqlite3?mode=ro',uri=True);db.row_factory=sqlite3.Row
receipt=dict(db.execute('select * from instance_policy_receipts where instance_id=? and generation=?',(ident,gen)).fetchone());artifact=json.loads(receipt['artifact_json'])
events=Path('/s/instances')/ident/'control'/gen/'.actplane/events.jsonl'
for p in (events,events.parent):
    info=p.lstat();assert info.st_uid==0 and not info.st_mode&0o022 and not p.is_symlink()
raw=[json.loads(line) for line in events.read_text().splitlines()]
matched=[e for e in raw if e.get('target')=='/w/0/sales.csv' and e.get('process_domain_id')==domain]
assert len(matched)>=7 and all(e['blocked'] and e['action']=='block' and e['op']=='write' for e in matched)
refs=artifact['compile']['rules'];assert all(any(e['rule']['source_ref']==c['source_ref'] and e['rule']['clause_hash']==c['clause_hash'] for c in refs) for e in matched)
assert all(e.get('provenance',{}).get('origin_pid')==r['after_application']['pid'] for e in matched)
assert len([e for e in page['records'] if e['target']=='/w/0/sales.csv' and e['source_refs']])==len(matched)
native=Path('/s/instances')/ident/'state/.dsh/sessions/--w-0--'/sid/'session.v4.jsonl.zstd'
transcript=[]
for line in decompress(native.read_bytes()).splitlines():
    e=json.loads(line);d=e.get('data',{})
    if e.get('type')=='tool/call':transcript.append({'type':'tool/call','name':d.get('name'),'arguments':d.get('arguments')})
    if e.get('type')=='tool/result':transcript.append({'type':'tool/result','text':'\n'.join(x.get('text','') for x in d.get('message',{}).get('content',[]) if x.get('type')=='text')})
assert all(any(t.get('name')=='bash' and ('probe.py '+phase) in str(t.get('arguments')) for t in transcript) for phase in ('baseline','pending','applied'))
approval=api('/api/console/approvals/'+r['readonly_proposal']);assert approval['status']=='applied'
deployment=json.loads(Path('/var/lib/agentscope-scope-demo/release-backups/agentscope-policy-semantics-20261011-222957/result.json').read_text())
deploy=runpy.run_path('/home/happy/projects/agentscope-policy-semantics-20261011/scripts/deploy_policy_semantics.py')
manifest=json.loads(Path(deployment['release'],'semantics-deployment.json').read_text())
assert deployment['published'] and deployment['broker_unchanged'] and deployment['other_ports_unchanged']
assert deployment['authority_before']==deployment['authority_after']
assert deploy['service'](deploy['UNIT'])==deployment['current_api']
assert deploy['service']('agentscope-scope-demo-broker.service')==manifest['broker']
assert deploy['listeners']()==[line.strip() for line in manifest['listeners']]
source=Path('/home/happy/projects/agentscope-policy-semantics-20261011')
assert deploy['files'](source/'backend/agentscope_app')==deploy['files'](Path(deployment['release'])/'backend/agentscope_app')
assert deploy['sha'](deploy['STATE']/'ui/index.html')==deploy['sha'](source/'frontend/dist/index.html')
write('deployment.json',{'release':deployment['release'],'published':True,'api':deployment['current_api'],
    'broker_pid':manifest['broker']['MainPID'],'broker_unchanged':True,'other_ports_unchanged':True,
    'authority_before_sha256':deploy['digest'](deployment['authority_before']),'authority_after_sha256':deploy['digest'](deployment['authority_after']),
    'live_source_matches':True,'frontend_index_sha256':deploy['sha'](source/'frontend/dist/index.html')})
summary={k:r[k] for k in ('instance_id','session_id','fixture','baseline','before_generation','after_generation','after_submission','pending_before','pending_after','after_application','applied_after','generated_dsl','semantic_check','generation_run','artifact_id','readonly_proposal')}
summary.update(phases={phase:r[phase+'_result'] for phase in ('baseline','pending','applied')},existing_before=r['existing_before'],existing_final=existing,
    kernel={'root_owned':True,'file':str(events),'mode':oct(stat.S_IMODE(events.stat().st_mode)),'sha256':hashlib.sha256(events.read_bytes()).hexdigest(),'matched_write_denials':len(matched),'domain_id':domain,'bundle_hash':receipt['bundle_hash'],'source_refs_verified':True,'origin_pid_verified':True,'tool_attribution':'shared_executor_unattributed','tool_call_tag':'0'},
    native={'file':str(native),'sha256':hashlib.sha256(native.read_bytes()).hexdigest(),'filtered_tool_records':len(transcript),'private_reasoning_exported':False},approval_state=approval['status'],passed=True)
write('acceptance.json',summary);write('native-tools.json',transcript);write('kernel-events.json',matched)
write('kernel-projection.json',{'records':[e for e in page['records'] if e['target']=='/w/0/sales.csv'],'coverage':page['coverage']})
print(json.dumps({'passed':True,'checks':23,'kernel_denials':len(matched),'original_instances_unchanged':list(existing),'output':str(out)}))

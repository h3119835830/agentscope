#!/usr/bin/env python3
"""Exercise system inheritance on 18003, restoring the exact saved documents.

Only adds a synthetic notify rule. Run during an authorized runtime acceptance
window: active controlled connections restart twice, stopped connections stay stopped.
"""
import json,os,pwd,sys,time,urllib.request,uuid
from pathlib import Path
RUNTIME=Path('/opt/agentscope-task-archive-20261007')
def api(path,body=None):
    req=urllib.request.Request('http://127.0.0.1:18003'+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=120) as response:return json.load(response)
def apply(documents):
    base=api('/api/security/system/dsl')
    candidate=api('/api/security/system/dsl/proposals',dict(documents=documents,base_hash=base['document_hash'],base_revision=base['revision'],request_key=uuid.uuid4().hex))
    assert candidate['state']=='pending',candidate['result']['error']
    result=api('/api/security/system/dsl/proposals/'+candidate['id']+'/confirm',dict(proposal_hash=candidate['proposal_hash']))
    assert result['state']=='applied'
    return result
def main():
    if os.getuid()!=0:raise SystemExit('Run as root; drops to the API user before application')
    sys.path.insert(0,str(RUNTIME/'scripts'));from scope_service import environment
    os.environ.update(environment());sys.path.insert(0,str(RUNTIME/'backend'))
    user=pwd.getpwnam('agentscope-api');os.initgroups(user.pw_name,user.pw_gid);os.setgid(user.pw_gid);os.setuid(user.pw_uid)
    from agentscope_app.instances import store,dsl_policy,sessions
    from agentscope_app.broker_client import call as broker
    before=api('/api/agent-instances')['instances'];active=[r['id'] for r in before if r['mode']=='controlled' and r.get('active')]
    stopped=[r['id'] for r in before if r['mode']=='controlled' and not r.get('active')]
    assert len(active)>=2,'Need two already-active connections; never starts a stopped one'
    original=api('/api/security/system/dsl')['documents']
    doc=dict(id='acceptance-'+uuid.uuid4().hex,name='system-inheritance-acceptance.dsl',original_dsl='source SYSTEM_ACCEPTANCE = exec "**"\nrule system-notice:\n notify read file "/w/0/.agentscope-dsl-notify.txt" if SYSTEM_ACCEPTANCE\n because "Synthetic system inheritance acceptance"\n',metadata={})
    report={'active_connections':active,'stopped_connections':stopped,'passed':False}
    try:
        report['apply']=apply([*original,doc]);bindings=[]
        for ident in active:
            row=api('/api/agent-instances/'+ident);saved=dsl_policy.receipt(ident,row['generation'])
            records=[r for r in dsl_policy.policy_records(saved['artifact'],active=row['active']) if r.get('document_id')==doc['id']]
            assert row['active'] and len(records)==1 and records[0]['active'] and records[0]['scope_type']=='system'
            assert all(r.get('binding_mode')=='locked' for r in records[0]['compiled_refs'])
            fixture=Path(row['resources'][0])/'.agentscope-dsl-notify.txt'
            driven=fixture.is_file() and '/dsl-acceptance-' in str(fixture)
            if driven:
                outcome=broker(dict(action='agent-instance-dsl-probe',instance_id=ident,generation=row['generation'],effect='notify'),timeout=20)['probe']
                assert outcome['outcome']['read_completed']
            for _ in range(5):sessions.collect_kernel(store.get(ident));time.sleep(.1)
            from agentscope_app import db
            with db.connect() as con:raw=con.execute('SELECT * FROM instance_kernel_events WHERE instance_id=? AND generation=? ORDER BY id DESC',(ident,row['generation'])).fetchall()
            matched=[sessions.project_kernel(row,saved,r) for r in raw]
            matched=[r for r in matched if r['effect']=='notify' and any(ref['source_ref']==records[0]['source_ref'] for ref in r['source_refs'])]
            if driven:assert matched,'Explicit system notification not observed in '+ident
            assert all(not e['blocked'] and not e['killed'] for e in matched)
            bindings.append(dict(instance_id=ident,generation=row['generation'],domain_id=row['domain_id'],bundle_hash=saved['bundle_hash'],source_ref=records[0]['source_ref'],loaded_binding_verified=True,explicit_probe=driven,matched_events=len(matched)))
        assert any(b['explicit_probe'] for b in bindings),'Need the isolated acceptance fixture, never reads a user workspace as a canary'
        report['bindings']=bindings
        assert all(not api('/api/agent-instances/'+ident).get('active') for ident in stopped)
        report['passed']=True
    finally:
        report['restore']=apply(original)
        assert api('/api/security/system/dsl')['documents']==original
        assert all(api('/api/agent-instances/'+ident).get('active') for ident in active)
        assert all(not api('/api/agent-instances/'+ident).get('active') for ident in stopped)
        report['original_documents_restored']=True
        path=Path('/var/lib/agentscope-scope-demo/report/dsl-system-acceptance.json');path.write_text(json.dumps(report,ensure_ascii=False,indent=2));path.chmod(0o600)
    print(json.dumps(report,ensure_ascii=False))
if __name__=='__main__':main()

#!/usr/bin/env python3
"""Fault-inject the durable applying-before-loader crash window in lab B only."""
import hashlib
import json
import os
import sqlite3
import time
import urllib.request
import uuid
from pathlib import Path
import policy_flow_acceptance_service as lab

ROOT=Path(__file__).resolve().parents[1]
BASE='http://127.0.0.1:18173'

def api(path,body=None):
    with urllib.request.urlopen(urllib.request.Request(BASE+path,data=json.dumps(body).encode() if body is not None else None,
        headers={'Content-Type':'application/json'}),timeout=120) as response:return json.load(response)

def state(ident):
    row=api('/api/agent-instances/'+ident);dsl=api('/api/agent-instances/'+ident+'/dsl')
    return {k:row.get(k) for k in ('id','pid','generation','gate','active','connected')}|{'revision':dsl['revision'],'document_hash':dsl['document_hash']}

def main():
    assert os.geteuid()==0
    agents=json.loads(Path('/tmp/asflow-accept-agents.json').read_text())
    assert len(agents)==2
    for agent in agents:
        assert api('/api/agent-instances/'+agent['id'])['resources']==['/mnt/c/Users/happy/Desktop/projects/asflow-accept-fixtures-20261013/shared']
    a,b=[agent['id'] for agent in agents]
    deadline=time.monotonic()+30
    while time.monotonic()<deadline:
        before={a:state(a),b:state(b)}
        if all(row['active'] for row in before.values()):break
        time.sleep(.5)
    else:raise AssertionError('Both synthetic test agents must be active')
    base=api('/api/agent-instances/'+b+'/dsl')
    doc={'id':'recovery-test','name':'中断恢复隔离验收','original_dsl':'source AGENT = exec "**/node"\nrule recovery-test:\n notify read file "/w/0/README.md" if AGENT\n because "Synthetic interrupted application"','metadata':{}}
    p=api('/api/agent-instances/'+b+'/dsl/proposals',{'documents':[doc],'base_hash':base['document_hash'],'base_revision':base['revision'],'request_key':uuid.uuid4().hex})
    assert p['state']=='pending'
    receipt=api('/api/console/approvals/'+p['id']+'/approve',{'proposal_hash':p['proposal_hash'],'request_key':uuid.uuid4().hex})
    assert state(a)==before[a] and state(b)==before[b]
    # Equivalent persisted state to apply after its CAS, before any loader call.
    # No candidate, prior configuration or execution receipt is forged.
    request={'candidate_hash':p['proposal_hash'],'approval_hash':receipt['approval_hash']}
    digest=hashlib.sha256(json.dumps(request,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
    with sqlite3.connect(lab.service.STATE/'demo.sqlite3') as con:
        assert con.execute("UPDATE policy_approval_decisions SET state='applying' WHERE approval_id=? AND state='approved'",(p['id'],)).rowcount==1
        con.execute('INSERT INTO policy_application_requests VALUES(?,?,?,?,?,?)',(p['id'],uuid.uuid4().hex,digest,'applying',None,'2026-10-13T00:00:00+00:00'))
    lab.reload_api()
    deadline=time.monotonic()+45
    while time.monotonic()<deadline:
        try:
            after={a:state(a),b:state(b)}
            if after[a]['active'] and after[b]['gate']=='paused':break
        except OSError:pass
        time.sleep(.5)
    else:raise AssertionError('Interrupted application pause did not recover')
    assert after[a]==before[a]
    assert not after[b]['active'] and after[b]['document_hash']==before[b]['document_hash'] and after[b]['revision']==before[b]['revision']
    detail=api('/api/console/approvals/'+p['id'])
    assert detail['approval_status']=='failed' and not detail['can_apply']
    output=ROOT/'docs/REVIEW/evidence/policy-flow-20261013/recovery.json'
    output.write_text(json.dumps({'method':'durable crash-window injection; no loader invoked','before':before,'after':after,'approval_id':p['id'],'candidate_not_applied':True,'auto_retry':False,'passed':True},ensure_ascii=False,indent=2))
    print(json.dumps({'passed':True,'paused_test_agent':b,'unaffected_agent':a}))

if __name__=='__main__':main()

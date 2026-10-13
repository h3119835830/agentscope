#!/usr/bin/env python3
"""Collect public test facts from the dedicated 18173 lab; exclude private reasoning.

Run after the browser generation/approval/apply walkthrough and the two synthetic
native probes. Only the fixed ASFLOW_RESULT2 JSON, receipt sequence numbers,
compiled rule matches and exact runtime identities leave the lab journal.
"""
import hashlib
import json
import os
import pwd
import re
import subprocess
import urllib.request
from compression import zstd
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
BASE='http://127.0.0.1:18173'
RUNTIME=Path('/run/asflow-accept-20261013')
TASKS=Path('/aft/instances')
OUTPUT=ROOT/'docs/REVIEW/evidence/policy-flow-20261013/runtime.json'

def api(path):
    with urllib.request.urlopen(BASE+path,timeout=15) as response:return json.load(response)

def broker(ident,generation):
    user=pwd.getpwnam('agentscope-api')
    def demote():os.initgroups(user.pw_name,user.pw_gid);os.setgid(user.pw_gid);os.setuid(user.pw_uid)
    code='import sys,socket;s=socket.socket(socket.AF_UNIX);s.settimeout(10);s.connect(sys.argv[1]);s.sendall(sys.stdin.buffer.read()+b"\\n");print(s.makefile("rb").readline().decode())'
    response=subprocess.run(['/usr/bin/python3','-c',code,str(RUNTIME/'broker.sock')],
        input=json.dumps({'action':'agent-instance-kernel-events','instance_id':ident,'generation':generation}),
        text=True,capture_output=True,check=True,timeout=15,preexec_fn=demote)
    value=json.loads(response.stdout)
    assert value['ok']
    return value['result']

def main():
    assert os.geteuid()==0
    evidence=json.loads(Path('/tmp/asflow-policy-flow-evidence.json').read_text())
    sessions=json.loads(Path('/tmp/asflow-native-sessions.json').read_text())
    results=[]
    for index,entry in enumerate(sessions):
        ident=entry['agent'];sid=entry['result']['sessionId']
        assert re.fullmatch(r'instance-[a-f0-9]{16}',ident) and re.fullmatch(r'session-[a-f0-9-]{36}',sid)
        row=api('/api/agent-instances/'+ident)
        assert row['active'] and row['resources']==['/mnt/c/Users/happy/Desktop/projects/asflow-accept-fixtures-20261013/shared']
        journal=TASKS/ident/'state/.dsh/sessions/--w-0--'/sid/'session.v4.jsonl.zstd'
        with zstd.open(journal,'rt') as stream:events=[json.loads(line) for line in stream if line.strip()]
        found=[]
        for event in events:
            if event['type']!='tool/result':continue
            for part in event['data'].get('message',{}).get('content',[]):
                if part.get('type')!='text':continue
                for line in part.get('text','').splitlines():
                    if line.startswith('ASFLOW_RESULT2 '):found.append((event['seq'],json.loads(line.split(' ',1)[1])))
        assert found
        sequence,outcome=found[-1]
        assert outcome['read_before']==outcome['read_after']==26 and outcome['continued']
        assert outcome['write_open_denied']==outcome['truncate_denied']==(index==0)
        if index==0:assert outcome['write_errno']==outcome['truncate_errno']=='EPERM'
        delivery=[{'seq':event['seq'],'through_seq':event['data']['throughSeq']} for event in events
                  if event['type']=='session-log-deepseek/delivery-accepted' and event['data'].get('throughSeq',-1)>=sequence]
        assert delivery and any(event['type']=='turn/end' and event['seq']>sequence for event in events)
        kernel=broker(ident,row['generation'])
        refs={(r['source_ref'],r['clause_hash']) for r in row['runtime']['policy_artifact']['compile']['rules'] if 'h_' in r.get('name','')}
        matches=[event['event'] for event in kernel['events'] if (event['event'].get('rule',{}).get('source_ref'),event['event'].get('rule',{}).get('clause_hash')) in refs]
        if index==0:assert matches and any(e.get('blocked') for e in matches)
        else:assert not matches
        policy=api('/api/console/agents/'+ident+'/sessions/'+sid+'/policies')
        assert policy['active'] and all(not record.get('hits') for record in policy['records'])
        results.append({'instance_id':ident,'session_id':sid,'generation':row['generation'],'pid':row['pid'],
            'bundle_hash':policy['bundle_hash'],'outcome':outcome,'tool_result_seq':sequence,
            'feedback_delivery':delivery,'later_tool_result_seqs':[e['seq'] for e in events if e['type']=='tool/result' and e['seq']>sequence],
            'turn_completed':True,'kernel_matches':matches,'session_policy_count':len(policy['records']),
            'session_unattributed_hits_hidden':True})
    evidence['runtime_probes']=results
    evidence['canary_sha256']=hashlib.sha256(Path(row['resources'][0],'sales.csv').read_bytes()).hexdigest()
    evidence['limits']=['Native tools share the instance executor; kernel events have no trusted per-session tag.',
                        'Delivery receipts prove native tool-result feedback reached the model; no separate structured ActPlane feedback receipt is claimed.',
                        'First probes hit the read-only mount (EROFS) in both agents; only probes after explicit synthetic write grants establish Agent-specific ActPlane enforcement.']
    evidence['passed']=True
    OUTPUT.write_text(json.dumps(evidence,ensure_ascii=False,indent=2))
    print(json.dumps({'passed':True,'agents':len(results),'output':str(OUTPUT)}))

if __name__=='__main__':main()
